"""Exercise real loopback requests, source corrections and immutable context history."""

from copy import deepcopy
import http.client
import json
from threading import Thread
from urllib.parse import urlencode
import psycopg2
from platform_core.review.http import WorkbenchServer


def exercise(workspace, root, directory, checkpoint, report):
    """Test a live HTTP adapter over a real source and isolated PostgreSQL.

    @param workspace Installed review module.
    @param root Project root with the actual PDF and Web assets.
    @param directory Output directory for acceptance artifacts.
    @param checkpoint Callback persisting the current isolated database.
    @param report Mutable report retaining observations on failure.
    @return Updated report with exact frozen and latest-revision identities.
    @raise AssertionError If behavior violates a review invariant.
    """
    # checks retains completed observations; failing toggles one simulated checkpoint error.
    checks, failing = report.setdefault("checks", {}), [False]

    def publish():
        """Inject one test-only persistence failure or save the isolated catalog."""
        if failing[0]:
            failing[0] = False
            raise OSError("fixture publication failure")
        checkpoint()

    server = WorkbenchServer(0, workspace, root / "web", publish, testing=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def expect(name, actual, expected):
        """Record one observable contract assertion.

        @param name Stable case name.
        @param actual Observed value.
        @param expected Required value.
        @raise AssertionError If the observation differs.
        """
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        checks[name] = "passed"

    def request(route, body=None, headers=None, binary=False):
        """Send a request on a fresh HTTP connection.

        @param route Local interface route.
        @param body JSON payload, raw bytes or None for GET.
        @param headers Optional transport overrides.
        @param binary Whether body already contains encoded bytes.
        @return Status, response headers and decoded JSON or raw bytes.
        """
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
        data = body if binary else json.dumps(body).encode() if body is not None else None
        values = {"Content-Type":"application/json", "X-Review-Token":server.token,
                  "Origin":f"http://127.0.0.1:{server.server_port}", **(headers or {})}
        try:
            connection.request("GET" if body is None else "POST", route, data, values)
            response = connection.getresponse()
            raw, response_headers = response.read(), dict(response.getheaders())
            result = json.loads(raw) if "application/json" in response_headers.get("Content-Type","") else raw
            return response.status, response_headers, result
        finally:
            connection.close()

    def ok(route, body=None):
        """Require a successful JSON operation.

        @param route Local route.
        @param body Optional operation payload.
        @return Decoded response.
        @raise AssertionError If the server rejects the operation.
        """
        status, _, result = request(route, body)
        if status != 200:
            raise AssertionError(f"{route}: {status}: {result}")
        return result

    def reject(name, route, body, code, headers=None):
        """Require a stable rejection diagnostic.

        @param name Acceptance case name.
        @param route Local route.
        @param body Submitted operation.
        @param code Expected diagnostic.
        @param headers Optional hostile transport headers.
        """
        status, _, result = request(route, body, headers)
        expect(name, (status >= 400, result.get("code")), (True, code))

    def change(current, patch):
        """Preview and confirm an exact, explicitly labeled fixture edit.

        @param current Workspace state observed by the test.
        @param patch Whitelisted changes.
        @return Workspace after the new revision.
        """
        identity = {"project":current["project"], "expected":current["revision"]}
        preview = ok("/api/preview", {**identity,"patch":patch})
        return ok("/api/commit", {**identity,"patch":patch,"token":preview["token"],
                  "actor":"acceptance-fixture","reason":"隔离工程验收，不代表用户数学确认。"})

    try:
        status, headers, html = request("/")
        expect("workbench_html", status == 200 and "来源核对" in html.decode(), True)
        expect("same_origin_policy", "frame-ancestors 'none'" in headers["Content-Security-Policy"], True)
        expect("isolated_catalog", ok("/api/catalog")["testing"], True)
        # Upload uses the actual paper through the same route as the browser.
        status, _, current = request("/api/import", (root / "examples/papers/case_11/source.pdf").read_bytes(),
                                    {"Content-Type":"application/pdf","X-Filename":"case_11.pdf"}, True)
        expect("actual_pdf_upload", status, 200)
        original, project = deepcopy(current), current["project"]
        report["project"] = project
        expect("all_candidates_present", len(current["state"]["items"]), 15)
        expect("new_candidates_not_confirmed", any(item["decision"] == "pending" for item in current["state"]["items"]), True)
        expect("prior_contract_retained", {choice["decision"] for choice in current["state"]["project_choices"]["choices"]}, {"confirmed"})
        identity = {"project":project,"expected":current["revision"]}
        preview = ok("/api/freeze-preview", identity)
        expect("incomplete_review_visible", bool(preview["blockers"]), True)
        reject("incomplete_freeze_rejected", "/api/freeze", {**identity,"token":preview["token"],"actor":"fixture"}, "review_incomplete")
        # Resolve a real source with both exact text and page geometry.
        item = current["state"]["items"][0]
        anchor = item["sources"][0]["anchors"][0]
        query = {"extraction":anchor["extraction_id"],"page":anchor["page"],"start":anchor["start"],"end":anchor["end"]}
        located = ok("/api/reference?" + urlencode(query))
        expect("source_quote_and_geometry", located["anchor"] == anchor and bool(located["boxes"]), True)
        status, _, png = request("/api/image?" + urlencode({"extraction":anchor["extraction_id"],"page":anchor["page"]}))
        expect("rendered_original_page", status == 200 and png.startswith(b"\x89PNG"), True)
        (directory / "source-page.png").write_bytes(png)
        # A preview must disclose the diff and affected goals without changing state.
        patch = {"items":{item["key"]:{"summary":item["summary"] + "（核对说明）","decision":"confirmed"}}}
        preview = ok("/api/preview", {**identity,"patch":patch})
        expect("field_diff_visible", any(edit["field"] == "summary" for edit in preview["changes"]), True)
        expect("affected_goals_visible", len(preview["affected_goals"]), 4)
        expect("preview_is_read_only", ok("/api/project?id=" + project)["revision"], current["revision"])
        reject("wrong_preview_digest", "/api/commit", {**identity,"patch":patch,"token":"0"*64,"actor":"fixture","reason":"test"}, "preview_mismatch")
        current = change(current, patch)
        expect("revision_created", current["revision"] != original["revision"], True)
        expect("original_revision_unchanged", ok("/api/project?" + urlencode({"id":project,"revision":original["revision"]}))["state"], original["state"])
        reject("stale_writer", "/api/commit", {**identity,"patch":patch,"token":preview["token"],"actor":"fixture","reason":"test"}, "revision_conflict")
        identity = {"project":project,"expected":current["revision"]}
        forged = deepcopy(item["sources"])
        forged[0]["anchors"][0]["quote"] = "invented theorem"
        reject("invented_source", "/api/preview", {**identity,"patch":{"items":{item["key"]:{"sources":forged}}}}, "invalid_source")
        reject("proof_status_not_editable", "/api/preview", {**identity,"patch":{"items":{item["key"]:{"proof_status":"proved"}}}}, "invalid_field")
        expanded = ok("/api/reference?" + urlencode({**query,"end":anchor["end"]+10}))["anchor"]
        current = change(current, {"items":{item["key"]:{"sources":[{"selector":"manual_range","kind":"prose","anchors":[expanded]}],
                                                          "decision":"confirmed"}}})
        expect("source_edit_audited", any(edit["field"] == "sources" for edit in current["audit"]["changes"]), True)
        selected = ["fig3_acceptance_soundness","fig3_exactness"]
        current = change(current, {"selected":selected,"primary":selected[0]})
        expect("multiple_goals_selected", current["state"]["selected"], selected)
        identity = {"project":project,"expected":current["revision"]}
        reject("invalid_primary", "/api/preview", {**identity,"patch":{"primary":"dm_optimality"}}, "invalid_selection")
        # Fixture confirmations are isolated and attributed; no actual user decision is synthesized.
        confirmations = {entry["key"]:{"decision":"confirmed"} for entry in current["state"]["items"] if entry["decision"] != "excluded"}
        current = change(current, {"items":confirmations})
        expect("review_gate_complete", current["blockers"], [])
        identity = {"project":project,"expected":current["revision"]}
        preview = ok("/api/freeze-preview", identity)
        frozen = ok("/api/freeze", {**identity,"token":preview["token"],"actor":"acceptance-fixture"})
        report["frozen_id"] = frozen["id"]
        expect("exact_goal_binding", [goal["key"] for goal in frozen["context"]["goals"]], selected)
        expect("unproved_status_preserved", frozen["context"]["proof_status"], "unproved")
        expect("formal_mapping_still_required", frozen["context"]["formalization_status"], "mapping_required")
        expect("author_material_excluded", all(entry["material_role"] in ("model_definition","analysis_definition")
               for entry in frozen["context"]["model"] + frozen["context"]["analysis"]), True)
        expect("freeze_idempotent", ok("/api/freeze", {**identity,"token":preview["token"],"actor":"fixture"})["id"], frozen["id"])
        expect("export_matches_freeze", ok("/api/frozen?id=" + frozen["id"] + "&download=1"), frozen)
        current = change(current, {"choices":{"integer_time":{"statement":"验收用范围变化：整数 tick 且有限观察窗口。"}}})
        expect("scope_change_pending", next(choice["decision"] for choice in current["state"]["project_choices"]["choices"]
               if choice["id"] == "integer_time"), "pending")
        expect("scope_change_invalidates_goals", all(entry["decision"] == "pending" for entry in current["state"]["items"]
               if entry["category"] == "goal"), True)
        expect("frozen_history_unchanged", ok("/api/frozen?id=" + frozen["id"]), frozen)
        variant = ok("/api/freeze-preview", {"project":project,"expected":current["revision"]})
        expect("variant_scope_explicit", variant["context"]["scope_status"], "reviewed_variant")
        reject("stale_freeze", "/api/freeze", {**identity,"token":preview["token"],"actor":"fixture"}, "revision_conflict")
        current = change(current, {"items":{"fig3":{"material_role":"author_proof","decision":"confirmed"}}})
        expect("author_proof_blocks_freeze", any("作者证明" in issue["message"] for issue in current["blockers"]), True)
        identity = {"project":project,"expected":current["revision"]}
        reject("foreign_origin", "/api/freeze-preview", identity, "forbidden", {"Origin":"https://foreign.example"})
        reject("foreign_host", "/api/freeze-preview", identity, "forbidden", {"Host":"foreign.example"})
        reject("missing_token", "/api/freeze-preview", identity, "forbidden", {"X-Review-Token":""})
        reject("oversized_request", "/api/freeze-preview", identity, "invalid_request", {"Content-Length":str(3*1024*1024)})
        failing[0] = True
        status, _, result = request("/api/projects", {"semantic_id":current["semantic_id"],"name":"checkpoint fixture"})
        expect("failed_checkpoint_not_acknowledged", (status,result["code"]), (503,"checkpoint_failed"))
        expect("checkpoint_retry", "project" in ok("/api/projects", {"semantic_id":current["semantic_id"],"name":"recovery fixture"}), True)
        try:
            with workspace.ledger.db, workspace.ledger.db.cursor() as cursor:
                cursor.execute("DELETE FROM review_freezes")
        except psycopg2.Error:
            expect("immutable_freeze_table", workspace.frozen(frozen["id"]), frozen)
        else:
            raise AssertionError("Frozen history was deleted")
        expect("no_proof_attempts_created", workspace.ledger.rows("SELECT count(*) AS n FROM attempts")[0]["n"], 0)
        report.update({"frozen":frozen,"latest_revision":current["revision"]})
        checkpoint()
        expect("graceful_http_stop", ok("/api/stop", {}), {"stopping": True})
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
    return report
