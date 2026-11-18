"""Own feedback submission, concrete proposal generation and verifiable historical reads."""

import json
from pathlib import Path
from uuid import uuid4

from platform_core.evidence.storage import encoded, sha
from platform_core.evidence.terms import Rejected
from .proposals import build, resolve


class FeedbackWorkspace:
    """Expose one shared Interface for feedback without modifying proof executions.

    @ivar derivations Existing W04 workspace owning original graphs and route selections.
    @ivar ledger Shared append-only database and content-addressed artifact store.
    """

    def __init__(self, derivations):
        """Bind the existing execution catalog.

        @param derivations DerivationWorkspace over an installed W04 catalog.
        """
        self.derivations,self.ledger = derivations,derivations.ledger

    def install(self):
        """Install feedback and proposal records after the W04 schema."""
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def submit(self, run, selection, target, text, actor, intent="auto"):
        """Persist exact feedback and a concrete proposal in one database transaction.

        @param run Original execution identity.
        @param selection Route revision seen by the author, including a historical revision.
        @param target Exact node, alignment or edge identity within the execution.
        @param text Original natural-language feedback, preserved without trimming.
        @param actor Human-readable author attribution.
        @param intent Supported local action or auto for an explained text interpretation.
        @return Saved proposal with provenance, differences and prospective impacts.
        @raise Rejected If the target, route, author or feedback cannot be bound.
        """
        if not isinstance(text,str) or not text.strip() or len(text)>8000:
            raise Rejected("invalid_feedback_text","反馈应为 1–8000 个字符的非空文本。")
        if not isinstance(actor,str) or not actor.strip() or len(actor)>80:
            raise Rejected("invalid_feedback_actor","请填写不超过 80 个字符的作者名称。")
        # @var original, route Verified execution and the exact historical selection viewed by the author.
        original = self.derivations.read(run)
        route = next((item for item in original["selection_history"] if item["id"] == selection),None)
        if route is None:
            raise Rejected("unknown_feedback_selection","路线版本不属于该运行。")
        addressed = resolve(original,target)
        mapped = self.derivations.mapping.open(original["mapping"])
        # @var request Original input has its own immutable identity independent of the generated proposal.
        request = {"id":uuid4().hex,"run":run,"selection":selection,"target":target,
                   "text":text,"actor":actor,"intent":intent}
        proposal = build(original,mapped["ir"],route,request)
        # @var files Snapshot the actual generator and mathematical inputs used in this submission.
        files = {"input/feedback.json":self.ledger.objects.put(encoded(request)),
                 "input/target.json":self.ledger.objects.put(encoded(addressed)),
                 "input/graph.json":self.ledger.objects.put(encoded(original["graph"])),
                 "input/selection.json":self.ledger.objects.put(encoded(route)),
                 "input/ir.json":self.ledger.objects.put(encoded(mapped["ir"]))}
        for name in ("service.py","proposals.py","service_progress.py","schema.sql"):
            files["implementation/"+name] = self.ledger.objects.put(Path(__file__).with_name(name).read_bytes())
        # @var source_keys Semantic items attached to the target or to both sides of a relation.
        node_keys = ([target["key"]] if target["kind"] == "node" else
                     [addressed["from"],addressed["to"]] if target["kind"] == "alignment" else
                     [*addressed["premises"],addressed["conclusion"]])
        source_keys = sorted({key for node in original["graph"]["nodes"] if node["key"] in node_keys for key in node["source_keys"]} |
                             {key for task in proposal["tasks"] for key in task.get("source_keys",[])})
        proposal.update(run=run,mapping=original["mapping"],freeze=original["freeze"],
                        review_revision=original["review_revision"],selection=selection,request=request,
                        target_snapshot=addressed,files=files,
                        sources={key:mapped["ir"]["bindings"][key] for key in source_keys if key in mapped["ir"]["bindings"]})
        # @var identity Exact proposal content address; publication never touches original graph tables.
        identity = self.ledger.objects.put(encoded(proposal))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("INSERT INTO derivation_feedback(id,run,selection,manifest) VALUES (%s,%s,%s,%s)",
                           (request["id"],run,selection,files["input/feedback.json"]))
            cursor.execute("INSERT INTO revision_proposals(id,feedback) VALUES (%s,%s)",(identity,request["id"]))
        return self.read(identity)

    def read(self, proposal):
        """Restore the saved result rather than rerunning today's proposal generator.

        @param proposal Content address of a previously published proposal.
        @return Verified proposal and a separately labeled current-route observation.
        @raise Rejected If an artifact or its original execution binding does not match.
        """
        return self._read(proposal)

    def _read(self, proposal, original=None, mapped=None):
        """Restore a proposal using verified shared inputs when reading a history batch.

        @param proposal Saved content address.
        @param original Optional execution already verified by this history request.
        @param mapped Optional mapping already verified for that execution.
        @return Saved proposal with the current selection observation.
        """
        # @var rows Database index binds the proposal to exactly one original submission.
        rows = self.ledger.rows("SELECT p.feedback,f.run,f.selection,f.manifest,p.created_at FROM revision_proposals p "
                                "JOIN derivation_feedback f ON f.id=p.feedback WHERE p.id=%s",(proposal,))
        if not rows:
            raise Rejected("unknown_proposal",str(proposal))
        row = rows[0]
        result = json.loads(self.ledger.objects.get(proposal))
        request = json.loads(self.ledger.objects.get(row["manifest"]))
        if (result["feedback"],result["run"],result["selection"]) != (row["feedback"],row["run"],row["selection"]) or result["request"] != request:
            raise Rejected("proposal_mismatch","提案与原反馈绑定不一致。")
        for digest in result["files"].values():
            self.ledger.objects.get(digest)
        # @var original Verified immutable graph; only the observation below uses its latest route.
        original = original if original is not None else self.derivations.read(row["run"])
        route = next(item for item in original["selection_history"] if item["id"] == row["selection"])
        mapped = mapped if mapped is not None else self.derivations.mapping.open(original["mapping"])
        expected = {"input/feedback.json":request,"input/target.json":resolve(original,request["target"]),
                    "input/graph.json":original["graph"],"input/selection.json":route,"input/ir.json":mapped["ir"]}
        if any(result["files"][name] != sha(encoded(value)) for name,value in expected.items()):
            raise Rejected("proposal_mismatch","提案输入与原运行不一致。")
        if (result["mapping"],result["freeze"],result["review_revision"]) != (original["mapping"],original["freeze"],original["review_revision"]):
            raise Rejected("context_mismatch","提案上下文不一致。")
        return {**result,"id":proposal,"created_at":row["created_at"].isoformat(),
                "observation":{"current_selection":original["selection"]["id"],
                               "based_on_historical_selection":original["selection"]["id"] != row["selection"]}}

    def history(self, run):
        """List saved proposals for an execution without recomputing their contents.

        @param run Original derivation execution identity.
        @return Ordered proposal summaries with authors and exact addressed targets.
        """
        # @var original, mapped Verify shared proof artifacts once for the entire history response.
        original = self.derivations.read(run)
        mapped = self.derivations.mapping.open(original["mapping"])
        # @var rows Content addresses sorted by submission time for stable restoration.
        rows = self.ledger.rows("SELECT p.id FROM revision_proposals p JOIN derivation_feedback f ON f.id=p.feedback "
                                "WHERE f.run=%s ORDER BY p.created_at,p.id",(run,))
        results = []
        for row in rows:
            proposal = self._read(row["id"],original,mapped)
            results.append({key:proposal[key] for key in ("id","created_at","title","status","selection")} |
                           {"target":proposal["request"]["target"],"actor":proposal["request"]["actor"]})
        return results
