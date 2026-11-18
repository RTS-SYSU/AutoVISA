"""Bind reviewed semantic revisions to typed IR and independently checked Rocq declarations."""

import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.rocq import Rocq, SAFE_LINES, MODELS
from platform_core.evidence.terms import Rejected
from .case11 import definitions, proposition, MODEL_BINDINGS
from .language import MappingFailure, source


class FormalMapping:
    """Translate the supported frozen contract without silently adopting semantic variants.

    @ivar workspace Review workspace providing verified historical freezes.
    @ivar ledger Shared immutable index and content-addressed storage.
    @ivar root Project directory containing the explicitly pinned mapping profile.
    @ivar profile Decoded mapping baseline and source-file identities.
    """

    def __init__(self, workspace, root):
        """Bind mapping to review history without invoking the proof toolchain.

        @param workspace ReviewWorkspace with source validation.
        @param root Project checkout containing configurations and W01 files.
        """
        self.workspace, self.ledger, self.root = workspace, workspace.ledger, Path(root)
        self.profile = json.loads((self.root / "configs/case11-ir-profile.json").read_bytes())

    def install(self):
        """Install append-only mapping receipts after the review schema."""
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def prepare(self, freeze):
        """Produce typed IR, exact source bindings and explicit unsupported-goal diagnostics.

        @param freeze Immutable frozen review identity.
        @return Analysis IR retaining every selected goal and all scope differences.
        @raise Rejected If source or historical review integrity fails.
        """
        # @var context Verified immutable semantic snapshot, never the mutable project head.
        context = self.workspace.frozen(freeze)["context"]
        # Global differences block the whole model; target-specific differences block only that goal.
        issues, items = [], {item["key"]:item for item in context["model"] + context["analysis"] + context["goals"]}
        for name, digest in self.profile["locks"].items():
            path = self.root / name
            if not path.is_file() or sha(path.read_bytes()) != digest:
                issues.append({"code":"mapping_input_drift","field":name,"message":"形式映射基线文件已变化，需重新审核映射。"})
        if context["source_sha256"] != self.profile["source_sha256"]:
            issues.append({"code":"unsupported_source","field":"source_sha256"})
        for key in self.profile["required_model"] + self.profile["required_analysis"]:
            if key not in items:
                issues.append({"code":"missing_definition","field":key})
        for item in context["model"] + context["analysis"]:
            issues.extend(self._differences(item))
        # @var expected_choices, actual_choices Complete scope statements compared without omissions.
        expected_choices = {choice["id"]:choice["statement"] for choice in self.profile["choices"]}
        actual_choices = {choice["id"]:choice["statement"] for choice in context["scope"]["choices"]}
        if actual_choices != expected_choices:
            issues.append({"code":"scope_variant","field":"scope","expected":expected_choices,"actual":actual_choices,
                           "message":"当前范围不等于已编码合同，不能绑定旧 Rocq 主目标。"})
        # bindings retains corrected source ranges and the exact review revision for every semantic item.
        bindings = {key:{"review_revision":context["revision"],"sources":item["sources"],
                         "summary":item["summary"],"normalized":item["normalized"],
                         "normalization_origin":item["normalization_origin"]} for key,item in items.items()}
        # @var goals Every selected target, including unsupported targets with explicit gaps.
        goals = []
        for item in context["goals"]:
            # @var gaps Goal-specific semantic differences; mapped is true only when all checks agree.
            gaps = self._differences(item)
            if item["key"] != self.profile["supported_goal"]:
                gaps.append({"code":"unsupported_goal","field":item["key"],"message":"此目标尚无已审核的 Rocq 编码。"})
            mapped = not issues and not gaps
            goals.append({"key":item["key"],"goal_revision":sha(encoded([freeze,item["key"],item])),
                          "status":"mapped" if mapped else "blocked","issues":issues + gaps,
                          "proposition":proposition() if mapped else None,
                          "rocq_declaration":"Mapped.mapped_goal" if mapped else None,
                          "proof_status":"unproved","source_binding":item["key"]})
        # @var count, status Number of supported targets and overall mapping coverage.
        count = sum(goal["status"] == "mapped" for goal in goals)
        status = "mapped" if count == len(goals) else "partial" if count else "blocked"
        # Kernel bindings pin definitions with exact file hashes; their meanings are not inferred from short summaries.
        kernel = {}
        for name, binding in MODEL_BINDINGS.items():
            path = "proofs/" + binding["file"]
            text = (self.root / path).read_text() if (self.root / path).is_file() else ""
            match = re.search(r"(?m)^(?:Definition|Inductive) " + re.escape(binding["symbol"]) + r"\b", text)
            kernel[name] = {**binding,"source_file":path,"sha256":self.profile["locks"][path],
                            "line":text[:match.start()].count("\n")+1 if match else None,
                            "review_revision":context["revision"]}
        # @var tree Serializable IR containing typed mathematics and frozen provenance.
        tree = {"schema_version":1,"profile":self.profile["name"],"freeze":freeze,"project":context["project"],
                "review_revision":context["revision"],"semantic_id":context["semantic_id"],
                "source_sha256":context["source_sha256"],"extraction_id":context["extraction_id"],
                "status":status,"issues":issues,"bindings":bindings,"scope":context["scope"],
                "kernel_bindings":kernel,"primary":context["primary"],"goals":goals,
                "definitions":[definition for definition in definitions() if all(key in items for key in definition["sources"])],
                "proof_status":"unproved",
                "domain":{"time":"Nat ticks","arrivals":"all legal finite or infinite populations; empty initial history",
                          "service_interval":"[release, deadline)","release_and_demand":"arbitrary within contract bounds",
                          "scheduler":"single unit-speed, preemptive, work-conserving DM; fixed task-index tie-break",
                          "acceptance":"finite accepts_from trace with t <= D and workload <= t at final point",
                          "positive_period_required":True}}
        if count:
            source(tree)  # Type-check the generated IR before any Rocq invocation.
        return tree

    def _differences(self, item):
        """Compare mathematical fields against the audited case_11 baseline.

        @param item Frozen model, method or goal candidate.
        @return Field-level differences, preserving both requested and supported values.
        """
        # @var baseline Reviewed field values for this stable semantic item key.
        baseline = self.profile["expected"].get(item["key"])
        if baseline is None:
            return [{"code":"unsupported_item","field":item["key"]}]
        return [{"code":"semantic_variant","item":item["key"],"field":field,"expected":expected,
                 "actual":item.get(field),"message":"未建立此修订与已编码定义的等价性。"}
                for field, expected in baseline.items() if item.get(field) != expected]

    def compile(self, freeze):
        """Archive IR and check mapped declarations in real Rocq and an isolated kernel process.

        @param freeze Verified frozen review identity.
        @return Saved translation receipt; theorem proof status always remains unproved.
        """
        # @var ir Typed mapping proposal; files retains content-addressed compilation evidence.
        ir = self.prepare(freeze)
        files = {"analysis-ir.json":self.ledger.objects.put(encoded(ir))}
        # Freeze the compiler and its baseline, making later history reads independent of live configurations.
        for name in ("language.py","case11.py","service.py","schema.sql"):
            files["compiler/" + name] = self.ledger.objects.put(Path(__file__).with_name(name).read_bytes())
        files["mapping-profile.json"] = self.ledger.objects.put((self.root / "configs/case11-ir-profile.json").read_bytes())
        for name in self.profile["locks"]:
            if (self.root / name).is_file():
                files[name] = self.ledger.objects.put((self.root / name).read_bytes())
        # @var receipt Translation result kept separate from scheduling proof outcomes.
        receipt = {"schema_version":1,"freeze":freeze,"review_revision":ir["review_revision"],"status":ir["status"],
                   "proof_status":"unproved","files":files,"commands":[],
                   "declaration_check":"not_run","correspondence_check":"not_run","goals":ir["goals"]}
        if ir["status"] != "blocked":
            try:
                with TemporaryDirectory(prefix="autorta-ir-") as temp:
                    # @var checker Pinned W02 compiler and foundational-library verifier.
                    checker = Rocq(self.root, Path(temp) / "checker", self.ledger.objects)
                    files["checker-profile.json"] = checker.profile_id
                    receipt["base_build"] = checker.base
                    # @var build, generated Isolated compiler directory and rendered source bytes.
                    build = Path(temp) / "translation"
                    build.mkdir()
                    generated = source(ir)
                    (build / "Mapped.v").write_text(generated, encoding="utf-8")
                    files["Mapped.v"] = self.ledger.objects.put(generated.encode())
                    # @var flags Explicit logical namespaces for this one compilation.
                    flags = [*checker.maps, "-Q",str(build),""]
                    checker.run(receipt,build,"ir-compile",["rocq","compile","-q",*flags,"Mapped.v"])
                    files["Mapped.vo"] = self.ledger.objects.put((build / "Mapped.vo").read_bytes())
                    # A second directory contains only verified .vo objects and the installed locked foundation.
                    recheck = Path(temp) / "recheck"
                    models = Path(temp) / "recheck-models"
                    models.mkdir(parents=True)
                    recheck.mkdir()
                    for name in MODELS:
                        (models / (name + ".vo")).write_bytes(self.ledger.objects.get(checker.base["files"]["models/" + name + ".vo"]))
                    (recheck / "Mapped.vo").write_bytes(self.ledger.objects.get(files["Mapped.vo"]))
                    # @var isolated_flags Nonoverlapping model and target load paths for fresh kernel checking.
                    isolated_flags = ["-Q",str(models),"AutoRTA","-Q",str(recheck),""]
                    # @var output Archived tool log used for strict kernel and assumption checks.
                    output = checker.run(receipt,recheck,"ir-kernel",["rocqchk",*isolated_flags,"-o","Mapped"])
                    # @var marker, summary Required context marker and kernel safety summary.
                    _, marker, summary = output.rpartition("CONTEXT SUMMARY")
                    if not marker or not (SAFE_LINES | {"* Axioms: <none>"}).issubset({line.strip() for line in summary.splitlines()}):
                        raise MappingFailure("unsafe_kernel","Unexpected kernel context")
                    # Verify the transitive modules reported by the independent kernel.
                    for loaded in re.findall(r"(?m)^\s*\[intern\s+(.+?\.vo)\s+\.\.\.", output):
                        # @var path, expected Actual loaded module and its approved content identity.
                        path = Path(loaded).resolve()
                        if path.parent == models and path.stem in MODELS:
                            expected = checker.base["files"]["models/" + path.name]
                        elif path == recheck / "Mapped.vo":
                            expected = files["Mapped.vo"]
                        elif path.is_relative_to(checker.coqlib):
                            expected = checker.foundation(path.relative_to(checker.coqlib).as_posix())
                        else:
                            raise MappingFailure("unapproved_dependency",str(path))
                        if sha(path.read_bytes()) != expected:
                            raise MappingFailure("dependency_mismatch",str(path))
                    # @var audit Independent query of the correspondence lemma assumptions.
                    audit = "Require Mapped.\nPrint Assumptions Mapped.target_matches.\n"
                    (recheck / "Audit.v").write_text(audit)
                    files["Audit.v"] = self.ledger.objects.put(audit.encode())
                    # @var output Archived tool log used for strict kernel and assumption checks.
                    output = checker.run(receipt,recheck,"ir-assumptions",["rocq","compile","-q",*isolated_flags,"Audit.v"])
                    if output != "Closed under the global context":
                        raise MappingFailure("unexpected_assumptions",output)
                    receipt["declaration_check"] = receipt["correspondence_check"] = "passed"
            except (MappingFailure, Rejected) as error:
                receipt["status"] = "failed"
                receipt["error"] = {"code":error.code,"message":str(error)}
        # @var identity Content address of the immutable mapping receipt.
        identity = self.ledger.objects.put(encoded(receipt))
        with self.ledger.db, self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO formal_mappings(id,freeze_id,status) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                           (identity,freeze,receipt["status"]))
        return {"id":identity, **receipt}

    def open(self, identity):
        """Restore a receipt and verify archived code, source and original revision bindings.

        @param identity Mapping receipt identity.
        @return Verified receipt with its typed IR.
        @raise MappingFailure If an index or source identity disagrees.
        """
        # @var rows Append-only index entry binding a receipt to its original freeze.
        rows = self.ledger.rows("SELECT * FROM formal_mappings WHERE id=%s", (identity,))
        if not rows:
            raise MappingFailure("unknown_mapping",identity)
        # @var receipt Archived evidence verified against its content address and database index.
        receipt = json.loads(self.ledger.objects.get(identity))
        if receipt["freeze"] != rows[0]["freeze_id"] or receipt["status"] != rows[0]["status"] or receipt["proof_status"] != "unproved":
            raise MappingFailure("mapping_mismatch",identity)
        for digest in receipt["files"].values():
            self.ledger.objects.get(digest)
        for digest in receipt.get("base_build",{}).get("files",{}).values():
            self.ledger.objects.get(digest)
        # @var context Verified immutable semantic snapshot, never the mutable project head.
        context = self.workspace.frozen(receipt["freeze"])["context"]
        # @var ir Historical typed mapping, independent of current compiler configuration.
        ir = json.loads(self.ledger.objects.get(receipt["files"]["analysis-ir.json"]))
        if ir["review_revision"] != context["revision"] or receipt["review_revision"] != context["revision"]:
            raise MappingFailure("mapping_mismatch","Review revision differs")
        return {"id":identity, **receipt,"ir":ir}

    def history(self, freeze):
        """List verified receipts for one immutable frozen context.

        @param freeze Frozen context identity whose mappings should be restored.
        @return Receipt summaries with checks, revision and retained diagnostics.
        """
        self.workspace.frozen(freeze)
        # rows is ordered independently of the current project head.
        rows = self.ledger.rows("SELECT id FROM formal_mappings WHERE freeze_id=%s ORDER BY created_at,id", (freeze,))
        # @var summaries Verified, bounded-field views displayed in the workbench history.
        summaries = []
        for row in rows:
            # receipt verifies the archived IR and every referenced source artifact before display.
            receipt = self.open(row["id"])
            summaries.append({key:receipt[key] for key in
                              ("id","status","review_revision","declaration_check","correspondence_check","proof_status")})
            summaries[-1]["issues"] = [issue for goal in receipt["goals"] for issue in goal["issues"]]
            if "error" in receipt:
                summaries[-1]["issues"].append(receipt["error"])
        return summaries
