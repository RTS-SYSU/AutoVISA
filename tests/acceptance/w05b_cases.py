"""Observe real HTTP decisions, proposal adoption, receipt inheritance and bounded continuation."""

import http.client
import json
from threading import Thread
from uuid import uuid4

import psycopg2
from platform_core.review.http import WorkbenchServer
from platform_core.evidence.terms import Rejected


def exercise(workspace, parent_id, checkpoint, report):
    """Exercise the W05-b Interface using actual W04 inputs and actual Rocq proof checks.

    @param workspace Installed ContinuationWorkspace over an isolated fixture catalog.
    @param parent_id Original W04 execution to preserve.
    @param checkpoint Durable fixture-dump callback.
    @param report Mutable acceptance observations and selected result identities.
    @return Original and child snapshots for an independent database-restore comparison.
    """
    # @var feedback, derivations, ledger Shared Interfaces; only this isolated fixture contains test decisions.
    feedback,derivations,ledger = workspace.feedback,workspace.derivations,workspace.ledger
    initial = derivations.read(parent_id)
    if initial["selection"]["choices"].get("goal/fig3_acceptance_soundness") != "via_witness":
        derivations.select(parent_id,initial["selection"]["id"],
                           {**initial["selection"]["choices"],"goal/fig3_acceptance_soundness":"via_witness"})
    original = derivations.read(parent_id)
    server = WorkbenchServer(0,derivations.mapping.workspace,derivations.mapping.root/"web",checkpoint,True)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()

    def expect(name, actual, wanted=True):
        """Record one behavioral assertion and print bounded progress.

        @param name Stable acceptance check identity.
        @param actual Observed value.
        @param wanted Required value.
        """
        if actual != wanted:
            raise AssertionError(f"{name}: {actual!r} != {wanted!r}")
        report["checks"][name] = "passed"
        if len(report["checks"]) % 10 == 0:
            print("W05-b checks passed:",len(report["checks"]),flush=True)

    def request(path, body=None, token=None):
        """Use the real Web route and exact request fields.

        @param path Local route and query.
        @param body Optional POST body.
        @param token Session-token override for rejection testing.
        @return HTTP status and decoded response.
        """
        # @var connection, headers Independent local request and actual server token.
        connection = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=600)
        headers = {"Content-Type":"application/json","X-Review-Token":server.token if token is None else token}
        try:
            connection.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body),headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status,json.loads(raw) if "application/json" in response.getheader("Content-Type","") else raw.decode()
        finally:
            connection.close()

    def propose(run, text, target=None):
        """Create feedback using the current selection of an explicitly identified fixture run.

        @param run Execution to address.
        @param text Original feedback.
        @param target Optional exact object, defaulting to the scheduling bridge.
        @return Saved W05-a proposal.
        """
        current = derivations.read(run)
        return feedback.submit(run,current["selection"]["id"],target or {"kind":"node","key":"response_bridge"},
                               text,"W05-b acceptance","auto")

    def command(proposal, decision=None, budget=12):
        """Prepare one stable adoption command.

        @param proposal Saved proposal record.
        @param decision Explicit latest decision or None.
        @param budget Maximum number of real W02 attempts in this child.
        @return User-visible command with a retry identity and exact plan token.
        """
        reviewed = workspace.review(proposal["id"])
        return {"proposal":proposal["id"],"preview":reviewed["plan"]["token"],"decision":decision,
                "budget":{"max_proof_attempts":budget},"actor":"W05-b acceptance","request_id":uuid4().hex}

    def adopt(body):
        """Run a concrete adoption and require a saved result.

        @param body Exact adoption command.
        @return Child execution returned through HTTP.
        """
        status,value = request("/api/adopt-proposal",body)
        if status != 200 or value.get("result") is None:
            raise AssertionError(f"Adoption failed: {status} {value}")
        return value["result"]

    try:
        split = propose(parent_id,"拆分调度桥接义务，保留原模型条件。")
        reviewed = request("/api/proposal-review?id="+split["id"])[1]
        expect("split_is_concrete_and_ready",reviewed["plan"]["ready"])
        expect("same_scope_split_no_extra_confirmation",reviewed["plan"]["requires_confirmation"],False)
        first_command = command(split)
        expect("adoption_requires_session_token",request("/api/adopt-proposal",first_command,token="wrong")[0],403)
        expect("plan_mismatch_rejected",request("/api/adopt-proposal",{**first_command,"preview":"0"*64})[1]["code"],"preview_mismatch")
        expect("independent_budget_validated",request("/api/adopt-proposal",{**first_command,"budget":{"max_proof_attempts":0}})[1]["code"],"invalid_run_budget")
        child = adopt(first_command)
        report.update(parent=parent_id,split_proposal=split["id"],child=child["id"])
        expect("linked_run_has_new_identity",child["id"] != parent_id)
        expect("parent_and_proposal_pinned",(child["parent"],child["proposal"],child["adoption"]),(parent_id,split["id"],first_command["request_id"]))
        expect("historical_input_is_not_independent_first_round",(child["execution"],child["initial_input_isolation"]),("local_continuation",False))
        expect("all_selected_roots_preserved",child["graph"]["roots"],original["graph"]["roots"])
        expect("scope_and_review_preserved",(child["mapping"],child["freeze"],child["review_revision"]),
               (original["mapping"],original["freeze"],original["review_revision"]))
        expect("split_has_two_new_obligations",len(child["graph"]["nodes"])-len(original["graph"]["nodes"]),2)
        repeated_split = propose(child["id"],"再次拆分调度桥接义务。")
        expect("already_split_feedback_needs_next_obligation",repeated_split["status"],"needs_details")
        # @var bridge_edge New sufficient implication must have a real checker receipt.
        bridge_edge = next(edge for edge in child["graph"]["edges"] if edge["key"] == "proposed_bridge_from_bounds")
        expect("joint_sufficiency_really_checked",bridge_edge["outcome"],"conditional")
        proof = derivations.evidence(child["id"],bridge_edge["attempt"])
        expect("new_proof_has_kernel_and_assumption_audit","Closed under the global context" in proof["assumptions"])
        expect("new_proof_retains_exact_type","service_from" in proof["exact_type"] and "all_deadlines_met" in proof["exact_type"])
        expect("new_run_is_partial",child["status"],"partial")
        main = next(item for item in child["plan"] if item["root"] == "goal/fig3_acceptance_soundness")
        expect("split_open_bounds_are_visible",set(main["open"]),{"proposed_service_lower","proposed_service_upper"})
        expect("confirmation_did_not_prove_root",main["status"],"unproved")
        expect("real_attempts_within_fixed_budget",1 <= child["usage"]["proof_attempts"] <= child["budget"]["max_proof_attempts"])
        expect("local_run_did_not_send_model_calls",child["usage"]["external_calls"],0)
        expect("legacy_unknown_cost_is_preserved",parent_id in child["cumulative_usage"]["unknown_cost_runs"])
        expect("parent_snapshot_unchanged",derivations.read(parent_id),original)
        if child["checker_profile"] != original["checker_profile"]:
            expect("profile_change_rechecks_all_original_receipts",all(item["disposition"] == "needs_recheck" for item in child["inheritance"]))
            expect("profile_change_creates_distinct_context",child["context"] != original["context"])
        else:
            expect("matching_profile_can_reuse_original_receipts",any(item["disposition"] == "reused" for item in child["inheritance"]))
        count = len(ledger.rows("SELECT id FROM attempts"))
        retried = adopt(first_command)
        expect("identical_retry_returns_same_run",retried,child)
        expect("retry_does_not_charge_or_check_again",len(ledger.rows("SELECT id FROM attempts")),count)
        expect("retry_cannot_change_budget",request("/api/adopt-proposal",{**first_command,"budget":{"max_proof_attempts":1}})[1]["code"],"request_conflict")
        # A second run with the same exact environment demonstrates actual receipt reuse.
        audit = propose(child["id"],"核对最小释放间隔条件。")
        reused = adopt(command(audit,budget=1))
        report["reused_child"] = reused["id"]
        expect("compatible_context_reused",reused["context"],child["context"])
        expect("eligible_receipts_reused",all(item["disposition"] == "reused" for item in reused["inheritance"]))
        expect("reuse_is_not_a_new_proof",reused["usage"]["proof_attempts"],0)
        expect("reused_receipt_links_retain_original_attempts",
               {item["attempt"] for item in reused["inheritance"]},
               {edge["attempt"] for edge in child["graph"]["edges"] if edge["attempt"]} |
               {attempt for node in child["graph"]["nodes"] for attempt in node["attempts"]})
        expect("cumulative_count_avoids_double_charging",reused["cumulative_usage"],child["cumulative_usage"])
        expect("parent_child_history",workspace.history(child["id"])[0]["run"],reused["id"])
        # Reverse alignment is concrete but cannot be adopted before an explicit content-bound decision.
        reverse = propose(child["id"],"反转这个对齐方向。",{"kind":"alignment","key":"trace_to_tasks"})
        reverse_command = command(reverse)
        expect("critical_change_waits_for_confirmation",request("/api/adopt-proposal",reverse_command)[1]["code"],"mathematical_confirmation_required")
        review = workspace.review(reverse["id"])
        decision_body = {"proposal":reverse["id"],"preview":review["plan"]["token"],"expected":None,
                         "choice":"reject","actor":"W05-b fixture reviewer","reason":"先保留原方向，补充核对。"}
        count = len(ledger.rows("SELECT id FROM attempts"))
        status,rejected = request("/api/proposal-decision",decision_body)
        expect("rejection_saved",status,200)
        expect("rejected_proposal_not_adopted",request("/api/adopt-proposal",{**reverse_command,"decision":rejected["id"]})[1]["code"],"decision_required")
        expect("stale_decision_write_rejected",request("/api/proposal-decision",{**decision_body,"choice":"confirm"})[1]["code"],"revision_conflict")
        status,confirmed = request("/api/proposal-decision",{**decision_body,"expected":rejected["id"],
            "choice":"confirm","reason":"确认仅采用反向待证连接；不把人工决定当作证明。"})
        expect("explicit_mathematical_confirmation_saved",status,200)
        expect("decision_pins_exact_plan",(confirmed["preview"],confirmed["parent"]),(review["plan"]["token"],rejected["id"]))
        expect("decision_is_not_proof_evidence",len(ledger.rows("SELECT id FROM attempts")),count)
        expect("confirmation_cannot_transfer_to_other_proposal",request("/api/adopt-proposal",{**command(audit),"decision":confirmed["id"]})[1]["code"],"revision_conflict")
        reversed_run = adopt({**reverse_command,"decision":confirmed["id"]})
        report.update(reverse_proposal=reverse["id"],confirmed_decision=confirmed["id"],reverse_run=reversed_run["id"])
        expect("critical_run_keeps_confirmation",reversed_run["decision"],confirmed["id"])
        alignment = reversed_run["graph"]["alignments"][0]
        expect("reversed_relation_is_only_pending",(alignment["from"],alignment["to"],alignment["status"],alignment["attempt"]),
               ("task_witnesses","trace_witness","candidate",None))
        expect("old_relation_absent_from_child",all(edge["key"] != "align_trace_to_tasks" for edge in reversed_run["graph"]["edges"]))
        witness = next(node for node in child["graph"]["nodes"] if node["key"] == "task_witnesses")
        inherited = next(item for item in reversed_run["inheritance"] if item["attempt"] == witness["complete"])
        expect("changed_actual_dependency_not_reused",inherited["disposition"],"needs_recheck")
        expect("changed_dependency_reason_visible","derivation_dependency_changed" in [item["code"] for item in inherited["reasons"]])
        expect("dependent_claim_reopened",not next(node for node in reversed_run["graph"]["nodes"] if node["key"] == "task_witnesses").get("complete"))
        expect("old_proof_remains_readable",derivations.evidence(child["id"],witness["complete"])["outcome"],"complete")
        expect("decision_history_retains_rejection_and_confirmation",[item["choice"] for item in workspace.review(reverse["id"])["decisions"]],["reject","confirm"])
        # A bounded execution ends honestly with its available partial evidence.
        limited = adopt(command(split,budget=1))
        report["budget_run"] = limited["id"]
        # The same limit can finish a one-check strategy when the baseline already uses today's profile.
        expected_end = "budget_exhausted" if child["checker_profile"] != original["checker_profile"] else "strategy_exhausted"
        expect("budget_limit_saves_partial_result",(limited["status"],limited["end_reason"],limited["usage"]["proof_attempts"]),
               ("partial",expected_end,1))
        expect("new_budget_does_not_change_parent",derivations.read(parent_id),original)
        expect("partial_result_keeps_all_goals",limited["graph"]["roots"],original["graph"]["roots"])
        scope = propose(parent_id,"把模型改为连续时间。")
        incomplete = workspace.review(scope["id"])
        expect("unformalized_scope_is_not_adoptable",incomplete["plan"]["ready"],False)
        expect("incomplete_scope_cannot_be_approved",request("/api/proposal-decision",{
            "proposal":scope["id"],"preview":incomplete["plan"]["token"],"expected":None,"choice":"confirm",
            "actor":"fixture","reason":"不能凭确认产生缺失的形式模型"})[1]["code"],"proposal_incomplete")
        expect("incomplete_scope_cannot_be_adopted",request("/api/adopt-proposal",command(scope))[1]["code"],"proposal_incomplete")
        for table in ("proposal_decisions","proposal_adoptions"):
            rejected_edit = False
            try:
                with ledger.db,ledger.db.cursor() as cursor:
                    cursor.execute("UPDATE "+table+" SET id=id WHERE false")
            except psycopg2.Error:
                rejected_edit = True
            expect(table+"_history_is_append_only",rejected_edit)
        expect("linked_runs_http_history",request("/api/linked-runs?run="+parent_id)[0],200)
        expect("original_feedback_still_immutable",feedback.read(split["id"])["adopted"],False)
        expect("adoption_state_is_separate",len(workspace.review(split["id"])["adoptions"]),2)
        # A real execution failure still owns a linked immutable run; the fixture supplies no fake proof success.
        previous_factory = derivations.checker_factory

        def unavailable(directory):
            """Represent a missing checker dependency for the isolated failure path.

            @param directory Private checker directory that would be allocated by a healthy dependency.
            @raise Rejected Always; this fixture cannot produce any proof receipt.
            """
            raise Rejected("checker_unavailable","W05-b fixture: checker is unavailable")

        derivations.checker_factory = unavailable
        try:
            failed = workspace.adopt(**command(split))["result"]
        finally:
            derivations.checker_factory = previous_factory
        expect("failed_execution_is_saved",(failed["status"],failed["end_reason"]),("failed","execution_failed"))
        expect("failed_execution_has_no_fake_proof",failed["usage"]["proof_attempts"],0)
        expect("failed_execution_keeps_parent_and_goals",(failed["parent"],failed["graph"]["roots"]),(parent_id,original["graph"]["roots"]))
        report["failed_run"] = failed["id"]
        # @var snapshots Saved mathematical and consent records must survive a fresh database process.
        snapshots = {key:derivations.read(key) for key in (parent_id,child["id"],reused["id"],reversed_run["id"],limited["id"],failed["id"])}
        checkpoint()
        return {"runs":snapshots,"review":workspace.review(reverse["id"])}
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
