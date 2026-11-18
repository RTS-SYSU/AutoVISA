"""Exercise feedback through the real HTTP adapter and inspect immutable mathematical artifacts."""

from copy import deepcopy
import http.client
import json
from threading import Thread

import psycopg2
from platform_core.review.http import WorkbenchServer


def exercise(workspace, run_id, checkpoint, report):
    """Check the complete submit-to-proposal workflow against restored real W04 evidence.

    @param workspace Installed FeedbackWorkspace using an isolated catalog.
    @param run_id Original W04 execution identity.
    @param checkpoint Durable database-dump callback.
    @param report Mutable acceptance report retaining each observed result.
    @return Final proposal and run snapshots to compare after independent restoration.
    """
    # @var original, ledger Original graph and proof store used to detect unintended adoption.
    original = workspace.derivations.read(run_id)
    ledger = workspace.ledger
    before_proofs = ledger.rows("SELECT id FROM attempts ORDER BY id")
    before_goals = ledger.rows("SELECT id FROM revisions ORDER BY id")
    server = WorkbenchServer(0,workspace.derivations.mapping.workspace,workspace.derivations.mapping.root/"web",checkpoint,True)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()

    def expect(name, actual, expected=True):
        """Retain an observed acceptance result or stop at a precise failure.

        @param name Stable check identity.
        @param actual Observed behavior or artifact.
        @param expected Required result.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        report["checks"][name] = "passed"
        if len(report["checks"]) % 10 == 0:
            print("W05-a checks passed:",len(report["checks"]),flush=True)

    def request(path, body=None, token=None):
        """Send a real local HTTP request using the workbench write contract.

        @param path Authored local route and query.
        @param body JSON body for POST, or None for GET.
        @param token Explicit token override for rejection checks.
        @return HTTP status and decoded content.
        """
        # @var connection, headers Per-request transport and actual process write token.
        connection = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=120)
        headers = {"Content-Type":"application/json","X-Review-Token":server.token if token is None else token}
        try:
            connection.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body),headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status,json.loads(raw) if "application/json" in response.getheader("Content-Type","") else raw.decode()
        finally:
            connection.close()

    def submit(text, target=None, intent="auto", selection=None):
        """Submit user feedback and require a concrete saved response.

        @param text Exact feedback including whitespace.
        @param target Optional addressed object, defaulting to the open scheduling bridge.
        @param intent Explicit or inferred local action.
        @param selection Historical route override, otherwise the current route.
        @return Verified saved proposal.
        """
        # @var current, body Execution context and the same fields submitted by the local form.
        current = workspace.derivations.read(run_id)
        body = {"run":run_id,"selection":selection or current["selection"]["id"],
                "target":target or {"kind":"node","key":"response_bridge"},"text":text,"actor":"W05-a acceptance","intent":intent}
        status,result = request("/api/feedback",body)
        if status != 200:
            raise AssertionError(f"Feedback failed: {status} {result}")
        return result

    try:
        expect("feedback_page", "feedback-form" in request("/reasoning")[1])
        expect("feedback_script_served",request("/feedback.js")[0],200)
        # @var split First proposal splits a bridge outside the currently selected direct-jobs route.
        exact = "  拆分这个调度桥接义务。\n保留原模型条件。  "
        split = submit(exact)
        report["example_proposal"] = split["id"]
        expect("original_feedback_preserved",split["request"]["text"],exact)
        expect("local_rule_explained",split["generator"],"local_rules")
        expect("concrete_split_created",(split["intent"],split["status"],len(split["preview"]["graph"]["nodes"])-len(original["graph"]["nodes"])),("split_bridge","draft",2))
        expect("new_claims_not_proved",all(not node.get("complete") and not node.get("goal") and node["attempts"] == []
                                        for node in split["preview"]["graph"]["nodes"] if node.get("proposed")))
        expect("proposal_type_and_structure_checks",split["checks"],{"structure":"passed","types":"passed","proof":"not_run"})
        expect("three_pending_checks",len([task for task in split["tasks"] if task["status"] == "open"]),3)
        expect("proposal_not_adopted",split["adopted"],False)
        bridge = next(node for node in original["graph"]["nodes"] if node["key"] == "response_bridge")
        expect("original_bridge_retained",next(node for node in split["preview"]["graph"]["nodes"] if node["key"] == "response_bridge"),bridge)
        # Replacing only the conclusion must leave every original quantified premise structurally identical.
        for node in [item for item in split["preview"]["graph"]["nodes"] if item.get("proposed")]:
            outer = deepcopy(node["statement"])
            tail = outer
            while tail["op"] == "forall":
                tail = tail["body"]
            while tail["right"]["op"] == "implies":
                tail = tail["right"]
            job = tail["right"]
            expect(node["key"]+"_universal_jobs",(job["op"],job["name"],job["sort"]),("forall","jid","Nat"))
            original_tail = bridge["statement"]
            while original_tail["op"] == "forall":
                original_tail = original_tail["body"]
            while original_tail["right"]["op"] == "implies":
                original_tail = original_tail["right"]
            tail["right"] = original_tail["right"]
            expect(node["key"]+"_preserves_outer_context",outer,bridge["statement"])
            expect(node["key"]+"_deadline_endpoint","release j" in node["formal"] and "deadline p" in node["formal"])
        expect("candidate_route_impact",split["impact"]["candidate_roots"],["goal/fig3_acceptance_soundness"])
        expect("inactive_route_excluded",split["impact"]["selected_roots"],[])
        expect("source_revision_binding",(split["mapping"],split["freeze"],split["review_revision"]),
               (original["mapping"],original["freeze"],original["review_revision"]))
        expect("source_excerpts_retained",any(binding["sources"] for binding in split["sources"].values()))
        expect("generator_archived","implementation/proposals.py" in split["files"])
        expect("http_proposal_reopens",request("/api/proposal?id="+split["id"]),(200,split))
        expect("submission_does_not_change_run",workspace.derivations.read(run_id),original)
        # A route change produces a new selection while the saved proposal keeps its prior impact.
        choices = {**original["selection"]["choices"],"goal/fig3_acceptance_soundness":"via_witness"}
        status,route = request("/api/select-route",{"run":run_id,"expected":original["selection"]["id"],"choices":choices})
        expect("existing_route_command",status,200)
        historical = workspace.read(split["id"])
        expect("historical_selection_labeled",historical["observation"]["based_on_historical_selection"])
        expect("historical_impact_preserved",historical["impact"],split["impact"])
        active = submit("拆分桥接义务。")
        expect("active_route_impact",active["impact"]["selected_roots"],["goal/fig3_acceptance_soundness"])
        old = submit("拆分桥接义务。",selection=original["selection"]["id"])
        expect("historical_submission_bound",old["selection"],original["selection"]["id"])
        expect("historical_submission_impact",old["impact"]["selected_roots"],[])
        # Condition review identifies its owner rather than inserting a new mathematical assumption.
        alignment = {"kind":"alignment","key":"trace_to_tasks"}
        audit = submit("检查最小释放间隔条件。",alignment)
        expect("condition_already_in_model",audit["status"],"reviewed_no_change")
        expect("condition_owners_include_bridge","response_bridge" in audit["tasks"][0]["owners"])
        expect("condition_source_binding",audit["tasks"][0]["kernel_binding"]["symbol"],"legal_arrivals")
        expect("condition_proposal_includes_its_own_sources",bool(audit["sources"]["sporadic_separation"]["sources"]))
        expect("condition_review_has_no_added_assumption",all(change["kind"] == "add_review_task" for change in audit["changes"]))
        review = submit("核对对齐方向和实例化。",alignment)
        expect("alignment_audit_exact",review["tasks"][0]["instantiation"],original["graph"]["alignments"][0]["instantiation"])
        reverse = submit("反转这个对齐方向。",alignment)
        expect("reverse_requires_confirmation",reverse["requires_math_confirmation"])
        change = reverse["changes"][0]
        expect("reverse_exact_direction",(change["after"]["from"],change["after"]["to"]),("task_witnesses","trace_witness"))
        expect("reverse_has_no_borrowed_proof",(change["after"]["attempt"],change["after"]["rule"],change["after"]["edge"]),(None,None,None))
        expect("reverse_pending_obligations",reverse["impact"]["new_obligations"],["prove_reverse_alignment","rebuild_instantiation"])
        expect("reverse_identifies_implication_recheck",any(item["object"] == "align_trace_to_tasks" and item["disposition"] == "recheck_on_adoption" for item in reverse["impact"]["evidence"]))
        scope = submit("把目标改为连续时间。")
        expect("scope_request_needs_formalization",(scope["status"],scope["requires_math_confirmation"]),("needs_details",True))
        expect("scope_text_retained",scope["changes"][0]["after"]["requested_text"],scope["request"]["text"])
        unrecognized = submit("请让这里更好理解。",{"kind":"node","key":"trace_guard"})
        expect("unrecognized_feedback_saved",(unrecognized["status"],unrecognized["changes"]),("needs_details",[]))
        expect("feedback_routed_to_forward_side",unrecognized["owner"],"forward")
        ambiguous = submit("拆分义务；改为连续时间。")
        expect("ambiguous_request_not_silently_applied",ambiguous["intent"],"clarify")
        negated = submit("不要拆分义务。")
        expect("negated_action_not_applied",negated["changes"],[])
        proof_request = submit("把主目标标记为已证明。",{"kind":"node","key":"goal/fig3_acceptance_soundness"})
        expect("status_request_is_not_a_proof",proof_request["checks"]["proof"],"not_run")
        edge_feedback = submit("请说明这个推导。",{"kind":"edge","key":"via_witness"})
        expect("edge_feedback_bound",edge_feedback["target_snapshot"]["key"],"via_witness")
        # Invalid commands fail without leaving incomplete feedback/proposal database records.
        valid = {"run":run_id,"selection":route["id"],"target":alignment,"text":"检查对齐方向","actor":"fixture","intent":"auto"}
        count = len(workspace.history(run_id))
        for name,patch,wanted in [
            ("unknown_target",{"target":{"kind":"node","key":"absent"}},404),
            ("invalid_target_shape",{"target":{"kind":[],"key":"x"}},422),
            ("unknown_selection",{"selection":"0"*64},404),
            ("empty_text",{"text":" \n "},422),
            ("invalid_intent",{"intent":"execute_code"},422),
            ("extra_http_field",{"approved":True},422)]:
            expect(name,request("/api/feedback",{**valid,**patch})[0],wanted)
        expect("feedback_requires_token",request("/api/feedback",valid,token="invalid")[0],403)
        expect("rejected_requests_not_persisted",len(workspace.history(run_id)),count)
        expect("history_exposes_all_proposals",len(request("/api/feedback?run="+run_id)[1]),count)
        expect("unknown_proposal",request("/api/proposal?id="+"0"*64)[0],404)
        expect("proof_attempts_unchanged",ledger.rows("SELECT id FROM attempts ORDER BY id"),before_proofs)
        expect("formal_goal_revisions_unchanged",ledger.rows("SELECT id FROM revisions ORDER BY id"),before_goals)
        expect("original_graph_unchanged",workspace.derivations.read(run_id)["graph"],original["graph"])
        expect("main_goal_still_unproved",workspace.derivations.read(run_id)["plan"][0]["status"],"unproved")
        fact = next(node for node in original["graph"]["nodes"] if node["key"] == "trace_witness")
        expect("original_proof_still_readable",request("/api/derivation-evidence?run="+run_id+"&attempt="+fact["complete"])[1]["outcome"],"complete")
        for table in ("derivation_feedback","revision_proposals"):
            rejected = False
            try:
                with ledger.db,ledger.db.cursor() as cursor:
                    cursor.execute("UPDATE "+table+" SET id=id WHERE false")
            except psycopg2.Error:
                rejected = True
            expect(table+"_append_only",rejected)
        # Corrupt only a proposal artifact inside this isolated test store, then restore its exact bytes.
        artifact = ledger.objects.root/split["id"]
        content = artifact.read_bytes()
        try:
            artifact.write_bytes(content+b" ")
            status,value = request("/api/proposal?id="+split["id"])
            expect("damaged_proposal_rejected",(status,value["code"]),(422,"artifact_mismatch"))
        finally:
            artifact.write_bytes(content)
        # @var saved Full records used to verify restoration in a fresh PostgreSQL instance.
        saved = {"history":workspace.history(run_id),"proposal":workspace.read(split["id"]),
                 "run":workspace.derivations.read(run_id)}
        checkpoint()
        return saved
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
