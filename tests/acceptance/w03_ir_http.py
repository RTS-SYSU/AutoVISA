"""Verify mapping routes through the real local HTTP adapter."""

import http.client
import json
from threading import Thread
from platform_core.review.http import WorkbenchServer


def exercise_http(workspace, root, freeze, blocked_freeze, receipt, expect):
    """Check HTTP mapping, historical restoration and same-origin protections.

    @param workspace Installed review and mapping storage.
    @param root Checkout containing the Web assets.
    @param freeze Supported frozen fixture identity.
    @param blocked_freeze Semantically changed fixture that cannot map.
    @param receipt Previously checked baseline receipt.
    @param expect Assertion callback retaining named observations.
    """
    # publications counts acknowledged writes; all data lives in the acceptance database.
    publications = []
    server = WorkbenchServer(0, workspace, root / "web", lambda:publications.append(True), testing=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(route, body=None, token=None):
        """Send a fresh request using the same protocol as the browser.

        @param route Local API path with encoded hexadecimal identities.
        @param body Optional JSON value; absence selects GET.
        @param token Optional token override for the rejection fixture.
        @return HTTP status and decoded JSON response.
        """
        # connection is closed after each request, avoiding shared transport state.
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
        headers = {"Content-Type":"application/json","X-Review-Token":server.token if token is None else token}
        data = None if body is None else json.dumps(body).encode()
        try:
            connection.request("GET" if body is None else "POST",route,data,headers)
            response = connection.getresponse()
            return response.status,json.loads(response.read())
        finally:
            connection.close()

    try:
        # Preview creates no receipt or durable write.
        status, preview = request("/api/map-preview",{"freeze":freeze})
        expect("http_preview_matches_baseline",(status,preview["status"]),(200,"mapped"))
        expect("http_preview_read_only",len(publications),0)
        status, restored = request("/api/mapping?id=" + receipt["id"])
        expect("http_receipt_restores_revision",(status,restored["ir"]["review_revision"]),(200,receipt["review_revision"]))
        status, history = request("/api/mappings?freeze=" + freeze)
        expect("http_history_survives_reload",(status,[entry["id"] for entry in history]),(200,[receipt["id"]]))
        status, failure = request("/api/map",{"freeze":freeze},token="invalid")
        expect("http_mapping_requires_token",(status,failure["code"]),(403,"forbidden"))
        status, blocked = request("/api/map",{"freeze":blocked_freeze})
        expect("http_blocked_mapping_retains_gaps",(status,blocked["status"],bool(blocked["goals"][0]["issues"])),(200,"blocked",True))
        expect("http_mapping_checkpointed",len(publications),1)
        status, invalid = request("/api/mapping?id=" + "0"*64)
        expect("http_unknown_receipt",(status,invalid["code"]),(404,"unknown_mapping"))
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
