"""A small Interface for concrete mathematical decisions, adoption and linked execution history."""

import json
from pathlib import Path
import re
from uuid import uuid4

from platform_core.evidence.storage import encoded
from platform_core.evidence.terms import Rejected
from .plans import prepare
from .execution import execute


class ContinuationWorkspace:
    """Own decision history and proposal adoption over the existing feedback and evidence modules.

    @ivar feedback W05-a Interface for immutable, source-bound proposals.
    @ivar derivations Existing graph and real-checker Interface.
    @ivar ledger Shared append-only history and content-addressed artifacts.
    """

    def __init__(self, feedback):
        """Bind an installed feedback workspace and its execution dependencies.

        @param feedback FeedbackWorkspace using the same local catalog.
        """
        self.feedback,self.derivations,self.ledger = feedback,feedback.derivations,feedback.ledger

    def install(self):
        """Install append-only decisions and adoption requests after the feedback schema."""
        # @var cursor Schema transaction, committed with the existing ledger connection.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("schema.sql").read_text())

    def _decisions(self, proposal):
        """Read original decisions in their recorded order.

        @param proposal Immutable proposal identity.
        @return Decision records with verified content addresses and creation times.
        """
        # @var rows Decision index; each content address also binds its predecessor.
        rows = self.ledger.rows("SELECT id,parent,created_at FROM proposal_decisions WHERE proposal=%s ORDER BY created_at,id",(proposal,))
        # @var result, row, record Ordered response, indexed decision and verified immutable content.
        result = []
        for row in rows:
            record = json.loads(self.ledger.objects.get(row["id"]))
            if record["proposal"] != proposal or record["parent"] != row["parent"]:
                raise Rejected("decision_mismatch","数学决定与提案或前序决定不一致。")
            result.append({**record,"id":row["id"],"created_at":row["created_at"].isoformat()})
        return result

    def _adoptions(self, proposal=None, parent=None):
        """Read linked execution summaries without rerunning proof construction.

        @param proposal Optional proposal filter.
        @param parent Optional parent-execution filter.
        @return Immutable adoption references with current saved execution outcomes.
        """
        # @var rows The result join distinguishes a registered execution from a finished partial result.
        rows = self.ledger.rows(
            "SELECT a.*,r.manifest AS result FROM proposal_adoptions a LEFT JOIN derivation_results r ON r.run=a.run "
            "WHERE (%s IS NULL OR a.proposal=%s) AND (%s IS NULL OR a.parent_run=%s) ORDER BY a.created_at,a.id",
            (proposal,proposal,parent,parent))
        # @var results, row, request, saved Summaries, adoption index, original command and optional finished result.
        results = []
        for row in rows:
            request = json.loads(self.ledger.objects.get(row["manifest"]))
            if (request["id"],request["proposal"],request["decision"],request["parent"]) != (
                row["id"],row["proposal"],row["decision"],row["parent_run"]):
                raise Rejected("adoption_mismatch","采用记录的输入绑定不一致。")
            saved = json.loads(self.ledger.objects.get(row["result"])) if row["result"] else None
            results.append({"id":row["id"],"run":row["run"],"parent":row["parent_run"],"proposal":row["proposal"],
                            "decision":row["decision"],"actor":request["actor"],"budget":request["budget"],
                            "status":saved["status"] if saved else "registered","end_reason":saved.get("end_reason") if saved else None,
                            "created_at":row["created_at"].isoformat()})
        return results

    def review(self, proposal):
        """Expose the precise plan a person is deciding about, plus all earlier decisions and adoptions.

        @param proposal Saved feedback proposal identity.
        @return Concrete plan, stable decision token, decision history and linked runs.
        """
        # @var proposed, original Verified immutable inputs; the latest route is only a labeled observation.
        proposed = self.feedback.read(proposal)
        original = self.derivations.read(proposed["run"])
        # @var plan, decisions Reproducible review content and its append-only human decision sequence.
        plan = prepare(proposed,original)
        decisions = self._decisions(proposal)
        return {"plan":plan,"decisions":decisions,"current_decision":decisions[-1] if decisions else None,
                "adoptions":self._adoptions(proposal=proposal),
                "based_on_historical_selection":proposed["observation"]["based_on_historical_selection"]}

    def decide(self, proposal, preview, expected, choice, actor, reason):
        """Append an explicit decision bound to a concrete proposal, graph, scope and base route.

        @param proposal Proposal whose mathematical changes the author has reviewed.
        @param preview Exact token returned by review().
        @param expected Last observed decision identity, or None for the first decision.
        @param choice confirm, reject or request_revision.
        @param actor Human-readable decision author.
        @param reason Author's explanation, retained verbatim.
        @return Saved decision, including its predecessor and exact reviewed plan identity.
        @raise Rejected If the plan is incomplete, changed or the previous decision has advanced.
        """
        self._author(actor)
        if choice not in ("confirm","reject","request_revision"):
            raise Rejected("invalid_decision","请选择确认、拒绝或要求修订。")
        if not isinstance(reason,str) or not reason.strip() or len(reason)>4000:
            raise Rejected("invalid_decision_reason","请填写本次数学决定的理由。")
        # @var reviewed, plan Current observations and the immutable mathematical content being reviewed.
        reviewed = self.review(proposal)
        plan = reviewed["plan"]
        if preview != plan["token"]:
            raise Rejected("preview_mismatch","待确认内容已变化，请重新查看具体差异。")
        if not plan["ready"] and choice == "confirm":
            raise Rejected("proposal_incomplete","尚未形成精确修订，不能确认采用。")
        # @var record The decision records content consent; it does not claim a mathematical proof.
        record = {"proposal":proposal,"preview":preview,"parent":expected,"choice":choice,"actor":actor,"reason":reason,
                  "plan":self.ledger.objects.put(encoded(plan)),"meaning":"approve_revision_not_proof"}
        # @var identity, cursor, current Content identity, serialized write transaction and last decision.
        identity = self.ledger.objects.put(encoded(record))
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("decision/"+proposal,))
            cursor.execute("SELECT id FROM proposal_decisions WHERE proposal=%s ORDER BY created_at DESC,id DESC LIMIT 1",(proposal,))
            current = cursor.fetchone()
            if (current["id"] if current else None) != expected:
                raise Rejected("revision_conflict","数学决定已更新，请先查看最新记录。")
            cursor.execute("INSERT INTO proposal_decisions(id,proposal,parent) VALUES (%s,%s,%s)",(identity,proposal,expected))
        return self._decisions(proposal)[-1]

    def adopt(self, proposal, preview, decision, budget, actor, request_id):
        """Adopt one exact revision into a separately budgeted linked run and execute available checks.

        @param proposal Immutable feedback proposal to adopt.
        @param preview Reviewed plan token.
        @param decision Latest explicit confirmation, required for a critical mathematical change.
        @param budget Object containing max_proof_attempts for this run only.
        @param actor Author initiating adoption and the associated run.
        @param request_id Stable client command identity; an identical retry returns the original run.
        @return Adoption identity, child run identity and its saved complete or partial execution.
        @raise Rejected If confirmation, plan, budget or retry binding is invalid.
        """
        self._author(actor)
        if (not isinstance(budget,dict) or set(budget) != {"max_proof_attempts"} or
            type(budget["max_proof_attempts"]) is not int or not 1 <= budget["max_proof_attempts"] <= 32):
            raise Rejected("invalid_run_budget","本轮证明检查次数应为 1–32 的整数。")
        if not isinstance(request_id,str) or not re.fullmatch("[0-9a-f]{32}",request_id):
            raise Rejected("invalid_request_id","采用请求缺少稳定身份。")
        # @var command Exact user command identifies a retry independently of changing current heads.
        command = {"proposal":proposal,"preview":preview,"decision":decision,"budget":budget,"actor":actor,"request_id":request_id}
        # @var previous Existing reservation, if this command is an idempotent retry.
        previous = self.ledger.rows("SELECT run,manifest FROM proposal_adoptions WHERE id=%s",(request_id,))
        if previous:
            return self._retry(request_id,command,previous[0])
        # @var reviewed, plan Current observations and the immutable mathematical content being reviewed.
        reviewed = self.review(proposal)
        plan = reviewed["plan"]
        if preview != plan["token"]:
            raise Rejected("preview_mismatch","采用内容与已查看提案不同，请重新核对。")
        if not plan["ready"]:
            raise Rejected("proposal_incomplete","；".join(plan["blockers"]))
        # @var proposed, original Reopen the exact inputs before reserving a distinct execution identity.
        proposed = self.feedback.read(proposal)
        original = self.derivations.read(plan["parent"])
        # @var identity, request New child identity and the exact command/plan binding retained for recovery.
        identity = uuid4().hex
        request = {"id":request_id,"command":command,"proposal":proposal,"preview":preview,"decision":decision,
                   "budget":budget,"actor":actor,"parent":original["id"],"base_selection":plan["selection"],
                   "plan":self.ledger.objects.put(encoded(plan))}
        # @var cursor, existing, head, selected Serialized reservation, concurrent retry and latest exact decision.
        with self.ledger.db,self.ledger.db.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("adoption/"+request_id,))
            cursor.execute("SELECT run,manifest FROM proposal_adoptions WHERE id=%s",(request_id,))
            existing = cursor.fetchone()
            if existing:
                # A concurrent retry observes the same reservation without starting another proof run.
                if json.loads(self.ledger.objects.get(existing["manifest"]))["command"] != command:
                    raise Rejected("request_conflict","相同采用请求身份不能携带不同内容。")
                identity = existing["run"]
            else:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",("decision/"+proposal,))
                cursor.execute("SELECT id FROM proposal_decisions WHERE proposal=%s ORDER BY created_at DESC,id DESC LIMIT 1",(proposal,))
                head = cursor.fetchone()
                selected = json.loads(self.ledger.objects.get(head["id"])) if head else None
                if (head["id"] if head else None) != decision:
                    raise Rejected("revision_conflict","采用操作须引用最新数学决定。")
                if selected and (selected["choice"] != "confirm" or selected["preview"] != preview):
                    raise Rejected("decision_required","提案已被拒绝、要求修订或确认内容已变化。")
                if plan["requires_confirmation"] and selected is None:
                    raise Rejected("mathematical_confirmation_required","请先确认具体数学变更，再采用提案。")
                cursor.execute("INSERT INTO derivation_runs(id,mapping) VALUES (%s,%s)",(identity,original["mapping"]))
                cursor.execute("INSERT INTO proposal_adoptions(id,proposal,decision,parent_run,run,manifest) VALUES (%s,%s,%s,%s,%s,%s)",
                               (request_id,proposal,decision,original["id"],identity,self.ledger.objects.put(encoded(request))))
        if existing:
            return self._retry(request_id,command,dict(existing))
        # @var result Durable child outcome; execution failure is saved as a failed run.
        result = execute(self.derivations,original,proposed,plan,request,identity)
        return {"adoption":request_id,"run":identity,"status":result["status"],"result":result}

    def _retry(self, identity, command, previous):
        """Resolve an already registered adoption without allocating another run or proof attempt.

        @param identity Stable adoption command identity.
        @param command Command repeated by the client.
        @param previous Existing database row with run and request-manifest identities.
        @return The original result, or an explicit registered state if execution has not finished.
        """
        if json.loads(self.ledger.objects.get(previous["manifest"]))["command"] != command:
            raise Rejected("request_conflict","相同采用请求身份不能携带不同内容。")
        # @var finished, result Presence of a durable outcome and its verified historical contents.
        finished = self.ledger.rows("SELECT run FROM derivation_results WHERE run=%s",(previous["run"],))
        result = self.derivations.read(previous["run"]) if finished else None
        return {"adoption":identity,"run":previous["run"],"status":result["status"] if result else "registered","result":result}

    def history(self, run):
        """List adopted child executions while retaining the parent's original run identity.

        @param run Parent execution whose continuation history is requested.
        @return Child adoption summaries, including failed and partial runs.
        """
        self.derivations.read(run)
        return self._adoptions(parent=run)

    @staticmethod
    def _author(actor):
        """Validate author attribution without claiming authentication in the local workbench.

        @param actor Human-readable author name supplied by the form or CLI.
        @raise Rejected If the attribution is empty or too long.
        """
        if not isinstance(actor,str) or not actor.strip() or len(actor)>80:
            raise Rejected("invalid_actor","请填写不超过 80 个字符的作者名称。")
