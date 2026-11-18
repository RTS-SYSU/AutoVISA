"""Observe version-bound comparisons through the same HTTP Interface used by the workbench."""

from copy import deepcopy
import http.client
import json
from threading import Thread

import psycopg2
from platform_core.review.http import WorkbenchServer
from platform_core.comparison.differences import changes


def exercise(workspace, baseline, checkpoint, report):
    """Compare actual saved W05-b runs and preserve every original proof record.

    @param workspace Installed ComparisonWorkspace over an isolated restored catalog.
    @param baseline Successful W05-b report identifying actual parent, child, reuse and failure cases.
    @param checkpoint Durable backup callback used by the HTTP adapter.
    @param report Mutable list of observed acceptance results.
    @return Saved comparison snapshots for independent database restoration.
    """
    # @var derivations, ledger, original_runs Verified historical inputs and their shared immutable store.
    derivations,ledger = workspace.derivations,workspace.ledger
    original_runs = {baseline[key]:derivations.read(baseline[key]) for key in
                     ("parent","child","reused_child","reverse_run","budget_run","failed_run")}
    # @var counts Baseline write counts prove that comparisons do not submit checks or rewrite history.
    counts = {table:len(ledger.rows("SELECT * FROM "+table)) for table in
              ("attempts","derivation_runs","derivation_results","derivation_selections","proposal_decisions","proposal_adoptions")}
    # @var server, thread Real loopback workbench sharing the same comparison Interface.
    server = WorkbenchServer(0,derivations.mapping.workspace,derivations.mapping.root/"web",checkpoint,True)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()

    def expect(name, actual, wanted=True):
        """Record an observed behavioral outcome.

        @param name Stable check identity.
        @param actual Observed result.
        @param wanted Required value.
        """
        if actual != wanted:
            raise AssertionError(f"{name}: {actual!r} != {wanted!r}")
        report["checks"][name] = "passed"
        if len(report["checks"]) % 10 == 0:
            print("W05-c checks passed:",len(report["checks"]),flush=True)

    def request(path, body=None, token=None):
        """Use actual HTTP routes and session protection.

        @param path Relative endpoint or page.
        @param body Optional exact POST command.
        @param token Optional override for CSRF rejection checks.
        @return HTTP status and JSON or text response.
        """
        # @var connection, response, raw Independent request with bounded lifetime.
        connection = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=600)
        try:
            connection.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body),
                {"Content-Type":"application/json","X-Review-Token":server.token if token is None else token})
            response = connection.getresponse()
            raw = response.read()
            return response.status,json.loads(raw) if "application/json" in response.getheader("Content-Type","") else raw.decode()
        finally:
            connection.close()

    def command(child):
        """Choose the adoption baseline and the child's explicit saved route.

        @param child Actual linked execution identity.
        @return Fully specified comparison command.
        """
        # @var choices Actual picker defaults, resolved once before creating a comparison.
        choices = workspace.options(child)
        return {"parent":choices["parent"]["id"],"child":child,"parent_selection":choices["parent"]["default_selection"],
                "child_selection":choices["child"]["default_selection"]}

    def save(child):
        """Create a comparison through the actual Web endpoint.

        @param child Linked execution to compare with its actual parent.
        @return Saved, content-addressed comparison.
        """
        # @var status, result Actual response, never a synthesized successful comparison.
        status,result = request("/api/comparisons",command(child))
        if status != 200:
            raise AssertionError(result)
        return result

    try:
        # @var split_command, status, split Exact versions and actual saved split comparison.
        split_command = command(baseline["child"])
        expect("comparison_page_served",request("/compare?child="+baseline["child"])[0],200)
        expect("comparison_script_served",request("/comparison.js")[0],200)
        expect("comparison_options_http",request("/api/comparison-options?child="+baseline["child"])[0],200)
        expect("creation_requires_session_token",request("/api/comparisons",split_command,"")[0],403)
        expect("versions_must_be_explicit",request("/api/comparisons",{**split_command,"parent_selection":None})[1]["code"],"explicit_versions_required")
        expect("foreign_route_rejected",request("/api/comparisons",{**split_command,"parent_selection":split_command["child_selection"]})[1]["code"],"unknown_selection")
        expect("wrong_parent_rejected",request("/api/comparisons",{**split_command,"parent":baseline["reused_child"]})[1]["code"],"parent_mismatch")
        expect("unlinked_run_rejected",request("/api/comparison-options?child="+baseline["parent"])[1]["code"],"not_linked_run")
        split = save(baseline["child"])
        report["split_comparison"] = split["id"]
        expect("exact_parent_route_bound",split["parent"]["selection"]["id"],split_command["parent_selection"])
        expect("exact_child_route_bound",split["child"]["selection"]["id"],split_command["child_selection"])
        expect("comparison_does_not_claim_new_proof_checks",split["proof_checks_submitted"],0)
        # @var diff, main Exact structural differences and the chosen main target's open leaves.
        diff = split["differences"]
        main = next(item for item in diff["obligations"] if item["root"] == "goal/fig3_acceptance_soundness")
        expect("same_model_is_explicit",diff["summary"]["model_changed"],False)
        expect("selected_targets_retained",diff["summary"]["goals_changed"],0)
        expect("new_bounds_visible",{row["key"] for row in diff["nodes"] if row["change"] == "added"},
               {"proposed_service_lower","proposed_service_upper"})
        expect("new_joint_edge_visible",any(row["key"] == "proposed_bridge_from_bounds" and row["change"] == "added" for row in diff["edges"]))
        expect("route_change_visible",any(row["key"] == "response_bridge" and row["after"] == "proposed_bridge_from_bounds" for row in diff["routes"]))
        expect("split_open_obligations",set(main["introduced"]),{"proposed_service_lower","proposed_service_upper"})
        expect("old_leaf_leaves_route_without_proof",main["left_route"],["response_bridge"])
        expect("no_fake_resolved_obligation",main["proved"],[])
        expect("root_remains_unproved",main["after"]["status"],"unproved")
        expect("rechecking_receipts_not_newly_proved_claims",diff["summary"]["newly_proved"],[])
        expect("conditional_joint_proof_retains_status",any(row["outcome"] == "conditional" and
               "edge:proposed_bridge_from_bounds" in row["after_owners"] for row in diff["receipts"]))
        expect("legacy_cost_unknown",diff["usage"]["before"]["external_cost_usd"],None)
        expect("unknown_cost_has_no_numeric_delta",diff["usage"]["delta"]["external_cost_usd"],None)
        expect("child_budget_recorded",diff["usage"]["after"]["budget"],{"max_proof_attempts":12})
        expect("cumulative_unknown_cost_retained",baseline["parent"] in diff["usage"]["after"]["cumulative"]["unknown_cost_runs"])
        expect("same_request_reopens_same_comparison",save(baseline["child"])["id"],split["id"])
        expect("immutable_read_matches_saved",request("/api/comparison?id="+split["id"])[1],split)
        # @var reuse, reverse, limited, failed Real parent-child variants use original historical receipts.
        reuse = save(baseline["reused_child"])
        reverse = save(baseline["reverse_run"])
        limited = save(baseline["budget_run"])
        failed = save(baseline["failed_run"])
        report.update(reuse_comparison=reuse["id"],reverse_comparison=reverse["id"],budget_comparison=limited["id"],failed_comparison=failed["id"])
        expect("reuse_does_not_count_new_receipts",reuse["differences"]["summary"]["new_receipts"],0)
        expect("reuse_reports_shared_original_receipts",reuse["differences"]["summary"]["shared_receipts"]>0)
        expect("reuse_does_not_reset_cumulative_usage",reuse["differences"]["usage"]["before"]["cumulative"],reuse["differences"]["usage"]["after"]["cumulative"])
        expect("reverse_direction_is_a_mathematical_change",reverse["differences"]["alignments"][0]["change"],"modified")
        expect("removed_alignment_edge_visible",any(row["key"] == "align_trace_to_tasks" and row["change"] == "removed" for row in reverse["differences"]["edges"]))
        expect("dependent_claim_reopened",reverse["differences"]["summary"]["reopened"],["task_witnesses"])
        expect("changed_actual_dependency_explained",any(
            item["change"] == "historical" and any(reason["code"] == "derivation_dependency_changed" for reason in item["inheritance"]["reasons"])
            for item in reverse["differences"]["receipts"] if item["inheritance"]))
        expect("original_confirmed_decision_bound",reverse["adoption"]["decision"],baseline["confirmed_decision"])
        expect("original_confirmation_is_not_proof",reverse["decision"]["meaning"],"approve_revision_not_proof")
        expect("limited_budget_is_separate",limited["differences"]["usage"]["after"]["budget"],{"max_proof_attempts":1})
        expect("failed_run_keeps_failure_status",failed["differences"]["usage"]["after"]["status"],"failed")
        expect("failed_run_has_no_new_evidence",failed["differences"]["summary"]["new_receipts"],0)
        for key,snapshot in original_runs.items():
            expect("original_run_unchanged_"+key,derivations.read(key),snapshot)
        for table,count in counts.items():
            expect("comparison_did_not_write_"+table,len(ledger.rows("SELECT * FROM "+table)),count)
        # @var current, moved Later route choices intentionally alter only isolated fixture heads.
        current = derivations.read(baseline["child"])
        moved = derivations.select(current["id"],current["selection"]["id"],
            {**current["selection"]["choices"],"goal/fig3_acceptance_soundness":"via_jobs"})
        expect("historical_read_uses_requested_route",derivations.read(current["id"],split_command["child_selection"])["selection"]["id"],split_command["child_selection"])
        expect("saved_comparison_stable_after_child_route_change",workspace.read(split["id"]),split)
        expect("original_record_link_pins_historical_route",request(split["child"]["links"]["record"])[1]["selection"]["id"],split_command["child_selection"])
        expect("original_view_link_pins_historical_route","selection="+split_command["child_selection"] in split["child"]["links"]["run"])
        current = derivations.read(baseline["parent"])
        derivations.select(current["id"],current["selection"]["id"],
            {**current["selection"]["choices"],"goal/fig3_acceptance_soundness":"via_jobs"})
        expect("saved_comparison_stable_after_parent_route_change",workspace.read(split["id"]),split)
        expect("picker_defaults_to_adoption_baseline",workspace.options(baseline["child"])["parent"]["default_selection"],split_command["parent_selection"])
        # @var changed New comparison explicitly requests the later child route while keeping the original parent baseline.
        changed = save(baseline["child"])
        expect("new_route_creates_distinct_comparison",changed["id"] != split["id"])
        expect("new_route_opens_direct_job_obligation",next(item for item in changed["differences"]["obligations"]
               if item["root"] == "goal/fig3_acceptance_soundness")["introduced"],["direct_jobs"])
        expect("old_snapshot_does_not_follow_new_comparison",workspace.read(split["id"]),split)
        expect("history_lists_both_versions",len(workspace.options(baseline["child"])["history"]),2)
        # @var receipt, side Source navigation actually resolves old and new evidence through the guarded route.
        for side in ("parent","child"):
            receipt = next(item for item in reverse["differences"]["receipts"] if item["before_owners" if side == "parent" else "after_owners"])
            expect(side+"_evidence_link_resolves",request("/api/derivation-evidence?run="+reverse[side]["run"]+"&attempt="+receipt["attempt"])[0],200)
        expect("mapping_record_link_resolves",request(split["parent"]["links"]["mapping"])[0],200)
        expect("frozen_record_link_resolves",request(split["child"]["links"]["freeze"])[0],200)
        # @var before, after Pure exact-value comparison tests unencoded goal/scope changes without inventing evidence.
        before = {"time":{"domain":"Nat","statement":"same title"}}
        after = deepcopy(before);after["time"]["domain"] = "Real"
        expect("same_label_different_math_is_modified",changes(before,after)[0]["change"],"modified")
        expect("added_removed_goal_identities_preserved",[row["change"] for row in changes({"a":None},{"b":None})],["removed","added"])
        # @var blocked, cursor Append-only index rejects edits even when no rows are selected.
        blocked = False
        try:
            with ledger.db,ledger.db.cursor() as cursor:
                cursor.execute("UPDATE run_comparisons SET id=id WHERE false")
        except psycopg2.Error:
            blocked = True
        expect("comparison_history_append_only",blocked)
        checkpoint()
        # @var saved Exact snapshots must survive a fresh database and a new workspace instance.
        saved = {item["id"]:item for item in (split,reuse,reverse,limited,failed,changed)}
        report["child"] = baseline["child"]
        report["reverse_run"] = baseline["reverse_run"]
        return saved
    finally:
        server.shutdown();thread.join(timeout=10);server.server_close()
