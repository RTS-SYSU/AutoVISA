"""A deep derivation workspace: independent expansion, alignment, evidence and history."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.service import Evidence
from platform_core.evidence.terms import Rejected
from . import graph


class DerivationWorkspace:
    """Own the executable W04 workflow behind derive, read, history and select.

    @ivar mapping W03 module resolving frozen, checked semantic mappings.
    @ivar ledger Shared content store and append-only evidence ledger.
    @ivar checker_factory Callable accepting a private directory and returning a real checker.
    """

    def __init__(self, mapping, checker_factory=None):
        """Bind storage and the proof-checking dependency.

        @param mapping Installed FormalMapping module for this catalog.
        @param checker_factory Checker constructor required only for derive().
        """
        self.mapping,self.ledger,self.checker_factory = mapping,mapping.ledger,checker_factory

    def install(self):
        """Install run and route-selection records after the W03 mapping schema."""
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def derive(self, mapping):
        """Execute independent local rules, align the graphs and check their proof constructions.

        @param mapping Successful W03 receipt identity, including partially supported goal sets.
        @return Saved run with all selected targets, checked facts and remaining obligations.
        @raise Rejected If the input is unmapped or the checker dependency is missing.
        """
        # @var mapped, ir Verified receipt and exact semantic revision consumed by both directions.
        mapped = self.mapping.open(mapping)
        ir = mapped["ir"]
        if mapped["status"] not in ("mapped","partial") or mapped["correspondence_check"] != "passed":
            raise Rejected("mapping_required","请先完成所选冻结上下文的形式映射。")
        if self.checker_factory is None:
            raise Rejected("checker_unavailable","No checker configured")
        if self.mapping.prepare(mapped["freeze"]) != ir:
            raise Rejected("mapping_changed","当前数学映射与已保存回执不同，请重新生成映射。")
        # @var identity Execution identity; independent repetitions retain independent proof attempts.
        identity = uuid4().hex
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO derivation_runs(id,mapping) VALUES (%s,%s)",(identity,mapping))
        # @var context Original reviewed source roles; full paper proof text is not supplied to either direction.
        context = self.mapping.workspace.frozen(ir["freeze"])["context"]
        materials = context["model"] + context["analysis"] + context["goals"]
        if any(item["material_role"] not in ("model_definition","analysis_definition","guarantee_statement") for item in materials):
            raise Rejected("material_scope","推导输入含有不属于模型、分析或目标的材料。")
        # @var shared Exact common mathematical input; each rule direction receives a separate deep copy.
        shared = {"schema_version":1,"mapping":mapping,"freeze":ir["freeze"],"review_revision":ir["review_revision"],
                  "ir":ir,"goals":ir["goals"],"materials":materials,
                  "material_policy":context["material_policy"],"execution":"local_rules"}
        files = {"input/shared.json":self.ledger.objects.put(encoded(shared))}
        for name in ("service.py","graph.py","statements.py","rules.py","schema.sql"):
            files["implementation/"+name] = self.ledger.objects.put(Path(__file__).with_name(name).read_bytes())
        # @var result Immutable execution record progressively populated with actual outputs and receipts.
        result = {"schema_version":1,"id":identity,"mapping":mapping,"freeze":ir["freeze"],
                  "review_revision":ir["review_revision"],"execution":"local_rules","status":"running",
                  "files":files,"events":[],"graph":{"nodes":[],"edges":[],"alignments":[],"roots":[]},"context":None}
        try:
            # Branch requests contain no peer output; only the alignment phase receives both candidate graphs.
            branches = {}
            for direction,execute in (("forward",graph.forward),("backward",graph.backward)):
                request = {**deepcopy(shared),"direction":direction,"peer_inputs":[]}
                request_id = self.ledger.objects.put(encoded(request))
                output = execute(request)
                output_id = self.ledger.objects.put(encoded(output))
                files["input/"+direction+".json"],files["output/"+direction+".json"] = request_id,output_id
                result["events"].append({"phase":direction,"input":request_id,"output":output_id,"kind":"executed_rule"})
                branches[direction] = output
            # @var alignments, connections Directed substitutions and their separately checked implications.
            alignments,connections = graph.align(branches["forward"],branches["backward"],shared)
            candidate = {"nodes":branches["forward"]["nodes"]+branches["backward"]["nodes"],
                         "edges":branches["forward"]["edges"]+branches["backward"]["edges"]+connections,
                         "alignments":alignments,"roots":branches["backward"]["roots"]}
            result["graph"] = candidate
            graph.validate(candidate,{})
            with TemporaryDirectory(prefix="autorta-w04-") as temporary:
                # @var checker, evidence Existing W02 checks and composition, reused for every graph claim.
                checker = self.checker_factory(Path(temporary)/"checker")
                evidence = Evidence(self.ledger,checker)
                result["checker_profile"] = checker.profile_id
                result["context"] = evidence.context("w04/"+identity,note=json.dumps(
                    {"mapping":mapping,"freeze":ir["freeze"],"input":files["input/shared.json"]},sort_keys=True))
                self._check(candidate,evidence,result)
            result["status"] = "completed" if all(
                item.get("complete") for item in candidate["nodes"] if item["key"] in candidate["roots"]) else "partial"
        except Exception as error:
            result["status"] = "failed"
            result["error"] = {"code":getattr(error,"code","execution_failed"),"message":str(error)}
        # @var manifest Final content address: execution history never changes when a route is selected later.
        manifest = self.ledger.objects.put(encoded(result))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO derivation_results(run,manifest) VALUES (%s,%s)",(identity,manifest))
        # @var choices Default routes prefer the witness decomposition and retain the direct backward alternative.
        choices = {}
        for item in result["graph"]["edges"]:
            choices.setdefault(item["conclusion"],item["key"])
        self.select(identity,None,choices)
        return self.read(identity)

    def _check(self, candidate, evidence, result):
        """Register exact graph goals and obtain real W02 receipts for rules and compositions.

        @param candidate Mutable graph receiving evidence identities and outcomes.
        @param evidence W02 module over the current checker and ledger.
        @param result Execution manifest collecting phase events.
        """
        # @var nodes Indexed claims; each proposition gets a run-specific immutable goal revision.
        nodes = {item["key"]:item for item in candidate["nodes"]}
        for item in nodes.values():
            if item["statement"] is not None:
                item["goal"] = evidence.goal("w04/"+result["id"]+"/"+item["key"],result["context"],
                                              {"analysis":item["statement"]})
        for relation in candidate["edges"]:
            # @var target, premises Exact target revision and every jointly required premise, in order.
            target = nodes[relation["conclusion"]]
            premises = [nodes[key]["goal"] for key in relation["premises"]]
            attempt = evidence.prove(target["goal"],{"derivation":relation["rule"]},premises)
            outcome = self.ledger.attempt(attempt)
            relation.update({"attempt":attempt,"outcome":outcome["code"],"detail":outcome["detail"]})
            result["events"].append({"phase":"check_rule","edge":relation["key"],"attempt":attempt,"outcome":outcome["code"]})
            if outcome["code"] == "complete":
                target["complete"] = attempt
                target["attempts"].append(attempt)
        # @var pending Conditional rules not yet composed; one successful round can enable another.
        pending = [relation for relation in candidate["edges"] if relation["outcome"] == "conditional"]
        while pending:
            ready = [relation for relation in pending if all(nodes[key].get("complete") for key in relation["premises"])]
            if not ready:
                break
            for relation in ready:
                target = nodes[relation["conclusion"]]
                attempt = evidence.compose(target["goal"],relation["attempt"],
                                           [nodes[key]["complete"] for key in relation["premises"]])
                outcome = self.ledger.attempt(attempt)
                target["attempts"].append(attempt)
                if outcome["code"] == "complete":
                    target["complete"] = attempt
                result["events"].append({"phase":"compose","edge":relation["key"],"attempt":attempt,"outcome":outcome["code"]})
                pending.remove(relation)
        for alignment in candidate["alignments"]:
            relation = next(item for item in candidate["edges"] if item["key"] == alignment["edge"])
            alignment["status"] = "checked" if relation["outcome"] == "conditional" else "rejected"
            alignment["attempt"] = relation["attempt"]

    def _saved(self, run):
        """Restore one execution and verify its original input and proof artifacts.

        @param run Execution identity.
        @return Immutable run manifest with verified graph evidence.
        @raise Rejected If a run, artifact or statement binding cannot be restored.
        """
        # @var rows Durable run identity and result content address.
        rows = self.ledger.rows("SELECT r.mapping,o.manifest FROM derivation_runs r JOIN derivation_results o ON o.run=r.id WHERE r.id=%s",(run,))
        if not rows:
            raise Rejected("unknown_run",run)
        result = json.loads(self.ledger.objects.get(rows[0]["manifest"]))
        if result["id"] != run or result["mapping"] != rows[0]["mapping"]:
            raise Rejected("run_mismatch",run)
        mapped = self.mapping.open(result["mapping"])
        if (mapped["freeze"],mapped["review_revision"]) != (result["freeze"],result["review_revision"]):
            raise Rejected("context_mismatch",run)
        for digest in result["files"].values():
            self.ledger.objects.get(digest)
        # Each loaded receipt must prove the node, or the exact ordered implication recorded on the edge.
        nodes = {item["key"]:item for item in result["graph"]["nodes"]}
        for item in nodes.values():
            if "goal" in item:
                revision = self.ledger.revision(item["goal"])
                if revision["body"]["proposition"] != {"analysis":item["statement"]} or revision["context"] != result["context"]:
                    raise Rejected("target_mismatch",item["key"])
            for attempt in item["attempts"]:
                saved = self.ledger.attempt(attempt)
                self.ledger.manifest(saved,verify=True)
                if saved["target"] != item["goal"] or (item.get("complete") == attempt and saved["code"] != "complete"):
                    raise Rejected("target_mismatch",item["key"])
        for relation in result["graph"]["edges"]:
            if relation["attempt"] is None:
                continue
            saved = self.ledger.attempt(relation["attempt"])
            self.ledger.manifest(saved,verify=True)
            if (saved["target"] != nodes[relation["conclusion"]]["goal"] or saved["code"] != relation["outcome"] or
                saved["request"]["premises"] != [nodes[key]["goal"] for key in relation["premises"]]):
                raise Rejected("dependency_mismatch",relation["key"])
        return result

    def read(self, run, selection=None):
        """Open a run at an explicit route revision, or its current revision when none is supplied.

        @param run Saved execution identity.
        @param selection Exact historical route identity, or None to resolve the latest route once.
        @return Graph, provenance, selected dependency closure and immutable selection history.
        """
        # @var result Verified candidate execution; selections are independent append-only revisions.
        result = self._saved(run)
        rows = self.ledger.rows("SELECT id FROM derivation_selections WHERE run=%s ORDER BY created_at,id",(run,))
        selections = [json.loads(self.ledger.objects.get(row["id"])) | {"id":row["id"]} for row in rows]
        # @var current Chosen immutable route; foreign or missing revisions never fall back to today's head.
        current = selections[-1] if selections else {"id":None,"choices":{}}
        if selection is not None:
            current = next((item for item in selections if item["id"] == selection),None)
            if current is None:
                raise Rejected("unknown_selection","路线版本不属于所选运行。")
        return {**result,"selection":current,"selection_history":selections,
                "plan":graph.plan(result["graph"],current["choices"])}

    def history(self, mapping):
        """List executions for one mapped frozen input.

        @param mapping Mapping receipt identity.
        @return Ordered saved run identities and their completion state.
        """
        self.mapping.open(mapping)
        # @var rows Run index ordered by execution creation time.
        rows = self.ledger.rows("SELECT r.id,r.created_at,o.manifest FROM derivation_runs r LEFT JOIN derivation_results o ON o.run=r.id "
                                "WHERE r.mapping=%s ORDER BY r.created_at,r.id",(mapping,))
        return [{"id":row["id"],"created_at":row["created_at"].isoformat(),
                 "status":self.read(row["id"])["status"] if row["manifest"] else "registered"} for row in rows]

    def select(self, run, expected, choices):
        """Append an exact route selection with optimistic concurrency.

        @param run Execution containing the immutable candidate graph.
        @param expected Current selection identity, or None for the initial selection.
        @param choices Complete conclusion-to-edge map for the new selection.
        @return Saved selection identity and its open joint premises.
        @raise Rejected If choices are cyclic, mismatched or based on a stale selection.
        """
        # @var result, plan Candidate execution and dependency closure for the requested routes.
        result = self._saved(run)
        plan = graph.plan(result["graph"],choices)
        selection = {"run":run,"parent":expected,"choices":choices}
        identity = self.ledger.objects.put(encoded(selection))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("selection/"+run,))
            cursor.execute("SELECT id FROM derivation_selections WHERE run=%s ORDER BY created_at DESC,id DESC LIMIT 1",(run,))
            row = cursor.fetchone()
            if (row["id"] if row else None) != expected:
                raise Rejected("revision_conflict","推导路线已更新，请重新加载后选择。")
            cursor.execute("INSERT INTO derivation_selections(id,run,parent) VALUES (%s,%s,%s)",(identity,run,expected))
        return {"id":identity,**selection,"plan":plan}

    def evidence(self, run, attempt):
        """Expose a checked proof and its exact type for a node or derivation in this run.

        @param run Execution whose graph owns the proof reference.
        @param attempt W02 attempt identity selected in that graph.
        @return Exact target, check outcome, readable generated sources and audit output.
        @raise Rejected If the reference belongs to another graph.
        """
        # @var result, allowed Verified graph and all actual rule or composition attempts it owns.
        result = self._saved(run)
        allowed = {edge["attempt"] for edge in result["graph"]["edges"]}
        allowed.update(attempt for node in result["graph"]["nodes"] for attempt in node["attempts"])
        if attempt not in allowed:
            raise Rejected("unknown_evidence",attempt)
        saved = self.ledger.attempt(attempt)
        receipt = self.ledger.manifest(saved,verify=True)
        return {"attempt":attempt,"target":saved["target"],"context":result["context"],
                "outcome":saved["code"],"detail":saved["detail"],"exact_type":receipt.get("exact_type"),
                "sources":{name:self.ledger.objects.get(digest).decode() for name,digest in receipt["files"].items()
                           if name.startswith("sources/") or (name.startswith("models/") and name.endswith(".v"))},
                "commands":receipt["commands"],"libraries":receipt.get("libraries",{}),
                "assumptions":self.ledger.objects.get(receipt["files"]["logs/assumptions"]).decode()
                              if "logs/assumptions" in receipt["files"] else None}
