"""Observe the actual Web derivation Interface with its real checker and checkpoint callback."""

import http.client
import json
from threading import Thread
from platform_core.review.http import WorkbenchServer


def execute(workspace, mapping, expect):
    """Derive through HTTP once, then inspect graph history and proof evidence.

    @param workspace Installed derivation workspace over the isolated test ledger.
    @param mapping Exact checked W03 receipt.
    @param expect Assertion callback retaining observations.
    @return Saved execution returned by the same command used by the browser.
    """
    # @var checkpoints Publications acknowledged by the local HTTP adapter.
    checkpoints = []
    server = WorkbenchServer(0,workspace.mapping.workspace,workspace.mapping.root/"web",
                             lambda:checkpoints.append(True),testing=True)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()

    def request(path, body=None, token=None):
        """Send a fresh local request with a bounded wait for actual proof compilation.

        @param path Authored HTTP route.
        @param body Optional JSON command; None selects GET.
        @param token Optional override used to test same-origin command protection.
        @return Status and decoded JSON or page text.
        """
        # @var connection, headers Per-request transport and the process-local write token.
        connection = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=600)
        headers = {"Content-Type":"application/json","X-Review-Token":server.token if token is None else token}
        try:
            connection.request("GET" if body is None else "POST",path,None if body is None else json.dumps(body),headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status,json.loads(raw) if "application/json" in response.getheader("Content-Type","") else raw.decode()
        finally:
            connection.close()

    try:
        status,page = request("/reasoning")
        expect("http_graph_page",(status,"双向推导工作区" in page),(200,True))
        status,rejection = request("/api/derive",{"mapping":mapping},token="invalid")
        expect("http_derive_requires_token",(status,rejection["code"]),(403,"forbidden"))
        status,run = request("/api/derive",{"mapping":mapping})
        expect("http_derivation_command",status,200)
        expect("http_derivation_checkpoint",len(checkpoints),1)
        status,reopened = request("/api/derivation?id="+run["id"])
        expect("http_graph_reopens",(status,reopened),(200,run))
        status,history = request("/api/derivations?mapping="+mapping)
        expect("http_execution_history",(status,history[0]["id"]),(200,run["id"]))
        # Inspect a complete fact through the user-visible evidence endpoint.
        fact = next(item for item in run["graph"]["nodes"] if item["key"] == "trace_witness")
        if fact.get("complete"):
            status,evidence = request("/api/derivation-evidence?run="+run["id"]+"&attempt="+fact["complete"])
            expect("http_exact_proof_evidence",(status,evidence["outcome"]),(200,"complete"))
            expect("http_assumption_audit","Closed under the global context" in evidence["assumptions"],True)
        status,rejection = request("/api/derivation?id="+"0"*32)
        expect("http_unknown_run",(status,rejection["code"]),(404,"unknown_run"))
        return run
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
