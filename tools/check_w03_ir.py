"""Acceptance for frozen semantic inputs, typed IR and real Rocq correspondence checking."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from paper_import import ROOT, BASE, write_json
from w02_postgres import database
from platform_core.evidence.storage import Ledger, sha
from platform_core.evidence.rocq import Rocq
from platform_core.evidence.terms import Rejected
from platform_core.paper_ingestion.models import SourceAnchor
from platform_core.paper_ingestion.pdf import Poppler
from platform_core.paper_ingestion.service import PaperImporter
from platform_core.semantics.service import SemanticExtractor
from platform_core.review.service import ReviewWorkspace
from platform_core.analysis_ir.service import FormalMapping
from platform_core.analysis_ir.language import MappingFailure, expression, SYMBOLS, source


def check_ir():
    """Run isolated mapping acceptance with real PDF, database and Rocq.

    @return Saved report path.
    @raise AssertionError If a required semantic or checker invariant fails.
    """
    # Every confirmation below is a marked fixture, separate from the user's working catalog.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    directory = BASE / "ir-checks" / stamp
    directory.mkdir(parents=True)
    report = {"status":"running","fixture_review":True,"checks":{}}

    def expect(name, actual, expected):
        """Retain an observable acceptance result.

        @param name Stable check identity.
        @param actual Observed value.
        @param expected Required value.
        @raise AssertionError If values differ.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        report["checks"][name] = "passed"

    def rejected(name, operation, code):
        """Require a specific typed-language or integrity rejection.

        @param name Acceptance identity.
        @param operation Zero-argument test action.
        @param code Expected diagnostic.
        """
        try:
            operation()
        except (MappingFailure, Rejected) as error:
            expect(name,error.code,code)
        else:
            raise AssertionError(name + " unexpectedly succeeded")

    try:
        with database() as (dsn, pg):
            ledger = Ledger(dsn,directory / "objects")
            try:
                ledger.install()
                importer = PaperImporter(ledger,Poppler())
                importer.install()
                semantic = SemanticExtractor(importer,ROOT)
                semantic.install()
                workspace = ReviewWorkspace(semantic)
                workspace.install()
                mapper = FormalMapping(workspace,ROOT)
                mapper.install()
                semantic_id = semantic.extract(importer.import_pdf(ROOT / "examples/papers/case_11/source.pdf"))

                def freeze_patch(patch=None):
                    """Create an independently confirmed fixture and optionally change its semantic content.

                    @param patch Optional content edits for the fixture's first review.
                    @return Frozen fixture identity.
                    """
                    current = workspace.create(semantic_id,"IR acceptance fixture")
                    edits = {"items":{item["key"]:{"decision":"confirmed"} for item in current["state"]["items"]
                                      if item["decision"] != "excluded"}}
                    for key,value in (patch or {}).items():
                        if key == "items":
                            for item,fields in value.items():
                                edits["items"].setdefault(item,{}).update(fields)
                        else:
                            edits[key] = value
                    prepared = workspace.prepare(current["project"],current["revision"],edits)
                    current = workspace.commit(current["project"],current["revision"],edits,prepared["token"],
                                               "acceptance-fixture","工程夹具确认，不代表用户数学确认。")
                    preview = workspace.preview_freeze(current["project"],current["revision"])
                    return workspace.freeze(current["project"],current["revision"],preview["token"],"acceptance-fixture")["id"]

                freeze = freeze_patch()
                ir = mapper.prepare(freeze)
                expect("baseline_maps",ir["status"],"mapped")
                expect("all_algorithm_definitions",len(ir["definitions"]),6)
                expect("exact_target_quantification",[ir["goals"][0]["proposition"]["name"],
                       ir["goals"][0]["proposition"]["body"]["name"],
                       ir["goals"][0]["proposition"]["body"]["body"]["name"]],["ts","a","s"])
                expect("source_identity_preserved",ir["source_sha256"],semantic.open(semantic_id).source_sha256)
                expect("source_ranges_resolve",all(importer.resolve(
                    SourceAnchor(**anchor)).anchor.quote == anchor["quote"]
                    for binding in ir["bindings"].values() for evidence in binding["sources"] for anchor in evidence["anchors"]),True)
                expect("all_bindings_pin_revision",all(binding["review_revision"] == ir["review_revision"] for binding in ir["bindings"].values()),True)
                expect("model_bindings_pin_code",all(binding["sha256"] and binding["line"] for binding in ir["kernel_bindings"].values()),True)
                # The positive path invokes the installed compiler and a separate kernel process.
                receipt = mapper.compile(freeze)
                write_json(directory / "mapping.json",receipt)
                expect("real_compiler_receipt",receipt["status"],"mapped")
                expect("real_declaration_check",receipt["declaration_check"],"passed")
                expect("real_correspondence_check",receipt["correspondence_check"],"passed")
                expect("main_goal_stays_unproved",receipt["proof_status"],"unproved")
                for name in ("Mapped.v","Audit.v"):
                    (directory / name).write_bytes(ledger.objects.get(receipt["files"][name]))
                write_json(directory / "analysis-ir.json",ir)
                report.update({"receipt":receipt["id"],"freeze":freeze,"review_revision":ir["review_revision"]})
                expect("freeze_not_mutated",workspace.frozen(freeze)["context"]["formalization_status"],"mapping_required")
                expect("no_proof_attempts",ledger.rows("SELECT count(*) AS n FROM attempts")[0]["n"],0)
                expect("repeat_preparation_stable",mapper.prepare(freeze),ir)
                # A source-only correction preserves semantics while retaining the corrected exact range.
                model_item = workspace.frozen(freeze)["context"]["model"][0]
                corrected_sources = deepcopy(model_item["sources"])
                anchor = corrected_sources[0]["anchors"][0]
                anchor["end"] -= 1
                anchor["quote"] = anchor["quote"][:-1]
                corrected_freeze = freeze_patch({"items":{model_item["key"]:{"sources":corrected_sources}}})
                corrected_ir = mapper.prepare(corrected_freeze)
                expect("source_correction_maps",corrected_ir["status"],"mapped")
                expect("corrected_source_retained",corrected_ir["bindings"][model_item["key"]]["sources"],corrected_sources)
                expect("old_source_stays_unchanged",mapper.open(receipt["id"])["ir"],ir)
                # A later revision of the same project must not retarget a saved receipt.
                current = workspace.read(ir["project"])
                patch = {"items":{"fig3_acceptance_soundness":{"summary":"仅同步轨迹的充分性。"}}}
                preview = workspace.prepare(current["project"],current["revision"],patch)
                workspace.commit(current["project"],current["revision"],patch,preview["token"],
                                 "acceptance-fixture","Engineering fixture only.")
                expect("old_receipt_survives_new_revision",mapper.open(receipt["id"])["ir"],ir)
                # Every unsupported selected goal remains visible instead of being silently discarded.
                mixed = freeze_patch({"selected":["fig3_acceptance_soundness","fig3_exactness"]})
                partial = mapper.prepare(mixed)
                expect("mixed_goals_partial",partial["status"],"partial")
                expect("unsupported_goal_retained",[goal["status"] for goal in partial["goals"]],["mapped","blocked"])
                expect("unsupported_has_no_fake_term",partial["goals"][1]["proposition"],None)
                changed = freeze_patch({"items":{"fig3":{"normalized":{
                    **next(item.normalized for item in semantic.open(semantic_id).items if item.key == "fig3"),
                    "initial":"t_0 = C_i"}}}})
                blocked = mapper.compile(changed)
                expect("wrong_initial_blocked",blocked["status"],"blocked")
                expect("blocked_does_not_invoke_checker",blocked["commands"],[])
                scope = freeze_patch({"choices":{"integer_time":{"statement":"连续实数时间。","decision":"confirmed"}}})
                expect("time_domain_change_blocked",mapper.prepare(scope)["status"],"blocked")
                # Even harmless prose changes need an explicit reviewed equivalence, not automatic alias reuse.
                prose = freeze_patch({"items":{"fig3_acceptance_soundness":{"summary":"仅同步轨迹的充分性。"}}})
                expect("weakened_goal_blocked",mapper.prepare(prose)["goals"][0]["status"],"blocked")
                rejected("unbound_ir_variable",lambda:expression({"op":"var","name":"x"},{},SYMBOLS),"unbound_variable")
                rejected("ill_typed_ir",lambda:expression({"op":"call","symbol":"taskset_wf","args":[{"op":"nat","value":1}]},{},SYMBOLS),"sort_mismatch")
                rejected("source_injection_rejected",lambda:expression({"op":"var","name":"x. Axiom injected:False."},{},SYMBOLS),"invalid_ir")
                # Delete the legal-arrivals premise from an otherwise well-typed IR. Rocq must reject correspondence.
                weakened = deepcopy(ir)
                body = weakened["goals"][0]["proposition"]["body"]["body"]["body"]
                body["right"] = body["right"]["right"]
                with TemporaryDirectory(prefix="autorta-ir-negative-") as temp:
                    checker = Rocq(ROOT,Path(temp)/"checker",ledger.objects)
                    build = Path(temp)/"negative"
                    build.mkdir()
                    text = source(weakened)
                    (build/"Mapped.v").write_text(text)
                    manifest = {"files":{},"commands":[]}
                    try:
                        checker.run(manifest,build,"missing-arrival-premise",["rocq","compile","-q",*checker.maps,"-Q",str(build),"","Mapped.v"])
                    except Rejected as error:
                        output = ledger.objects.get(manifest["files"]["logs/missing-arrival-premise"]).decode(errors="replace")
                        expect("kernel_rejects_missing_premise",error.code == "tool_failure" and
                               ("Unable to unify" in output or "not convertible" in output),True)
                    else:
                        raise AssertionError("Weakened target matched the original")
                    report["negative_check"] = manifest
                    (directory/"negative-correspondence.log").write_text(output)
                # Tampering a saved artifact must be detected even when no new mapping is requested.
                path = ledger.objects.root / receipt["files"]["Mapped.v"]
                saved = path.read_bytes()
                try:
                    path.write_bytes(b"changed")
                    rejected("tampered_rocq_rejected",lambda:mapper.open(receipt["id"]),"artifact_mismatch")
                finally:
                    path.write_bytes(saved)
                expect("old_receipt_after_other_freezes",mapper.open(receipt["id"])["ir"],ir)
                from w03_ir_http import exercise_http
                exercise_http(workspace,ROOT,freeze,changed,receipt,expect)
                pg("pg_dump","--format=custom","--no-owner","--file",directory/"history.dump",dsn)
            finally:
                ledger.close()
        # The original producing database is gone before this restore starts.
        with database() as (dsn, pg):
            pg("pg_restore","--exit-on-error","--no-owner","--dbname",dsn,directory/"history.dump")
            ledger = Ledger(dsn,directory/"objects")
            try:
                mapper = FormalMapping(ReviewWorkspace(SemanticExtractor(PaperImporter(ledger,Poppler()),ROOT)),ROOT)
                expect("independent_database_restore",mapper.open(report["receipt"])["ir"],ir)
            finally:
                ledger.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"],report["error"] = "failed",f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(directory/"report.json",report)
    write_json(BASE/"ir-checks/latest.json",{"run":stamp,"sha256":sha((directory/"report.json").read_bytes())})
    print(json.dumps({"status":"passed","checks":len(report["checks"]),"report":str(directory/"report.json")}))
    return directory/"report.json"
