"""Serve local review operations through the same interface used by acceptance tests."""

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit

from .service import ReviewFailure, require
from platform_core.analysis_ir.service import FormalMapping
from platform_core.reasoning.service import DerivationWorkspace
from platform_core.feedback.service import FeedbackWorkspace
from platform_core.continuation.service import ContinuationWorkspace
from platform_core.comparison.service import ComparisonWorkspace
from platform_core.evidence.rocq import Rocq
from platform_core.msa.service import MsaWorkspace
from platform_core.msa.mapping import CAPABILITIES
from platform_core.msa.expressions import parse as parse_expression
from platform_core.msa.pdf import MsaPoppler
from platform_core.paper_ingestion.service import PaperImporter


class WorkbenchServer(HTTPServer):
    """A loopback-only, sequential HTTP adapter for one local catalog.

    @ivar workspace ReviewWorkspace owning the server's database connection.
    @ivar assets Directory containing allowlisted static files.
    @ivar checkpoint Callback publishing a durable catalog before acknowledging writes.
    @ivar token Per-process CSRF token restricted to same-origin clients.
    @ivar testing Whether this is a visibly labeled acceptance catalog.
    @ivar images Bounded rendered-page cache indexed by extraction and page.
    @ivar persistence_failed Whether catalog publication needs retrying.
    """

    def __init__(self, port, workspace, assets, checkpoint, testing=False):
        """Bind the workbench to IPv4 loopback.

        @param port Local port, or zero for an ephemeral test port.
        @param workspace Installed review module.
        @param assets Static asset directory.
        @param checkpoint Zero-argument durable publication callback.
        @param testing Visible label for isolated acceptance data.
        """
        self.workspace, self.assets, self.checkpoint = workspace, Path(assets), checkpoint
        self.token, self.testing = secrets.token_urlsafe(32), testing
        self.images, self.persistence_failed = {}, False
        # @var msa Additive semantic workspace sharing the established durable catalog.
        self.msa = MsaWorkspace(workspace.ledger,self.assets.parent)
        self.msa.install()
        super().__init__(("127.0.0.1", port), WorkbenchHandler)


class WorkbenchHandler(BaseHTTPRequestHandler):
    """Translate local HTTP requests into source review operations."""

    def setup(self):
        """Bound socket reads so an interrupted request cannot hold the local workbench indefinitely."""
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format, *args):
        """Suppress request logging to keep source text and tokens out of logs.

        @param format Standard HTTP log format.
        @param args Standard HTTP log arguments, intentionally unused.
        """
        return

    def _guard(self, write=False):
        """Reject foreign hosts, origins and writes without a session token.

        @param write Whether to require the per-process CSRF token.
        @raise ReviewFailure If the host, origin or token is invalid.
        """
        # hosts contains only actual loopback endpoints, preventing external DNS aliases.
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        require(self.headers.get("Host") in hosts, "forbidden", "只接受本机工作台地址")
        origin = self.headers.get("Origin")
        require(origin is None or origin in {"http://" + host for host in hosts},
                "forbidden", "不接受其他网站发起的操作")
        if write:
            require(secrets.compare_digest(self.headers.get("X-Review-Token", ""), self.server.token),
                    "forbidden", "工作台会话已变化，请刷新页面")

    def _send(self, status, value, mime="application/json; charset=utf-8", filename=None):
        """Return content with same-origin browser protections.

        @param status HTTP status code.
        @param value JSON-compatible value or encoded bytes.
        @param mime Response content type.
        @param filename Optional trusted download filename.
        """
        # data is encoded once so Content-Length counts bytes instead of characters.
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, error):
        """Return a safe diagnostic without private paths or tracebacks.

        @param error Exception raised during the operation.
        """
        # code selects response status; unknown exceptions retain only a generic public message.
        code = getattr(error, "code", "request_failed")
        status = 403 if code == "forbidden" else 409 if code in ("revision_conflict", "preview_mismatch") else 422
        if code.startswith("unknown_"):
            status = 404
        if code == "checkpoint_failed":
            status = 503
        message = str(error) if hasattr(error, "code") else "请求处理失败，请检查输入；运行日志可供开发者诊断。"
        self._send(status, {"code": code, "message": message})

    def _reasoning(self):
        """Bind the derivation Interface to this catalog and its actual checker.

        @return DerivationWorkspace sharing immutable source and evidence storage.
        """
        # @var mapping Upstream module pinned to the current project checkout.
        mapping = FormalMapping(self.server.workspace,self.server.assets.parent)
        return DerivationWorkspace(mapping,lambda directory:Rocq(mapping.root,directory,mapping.ledger.objects))

    def _continuation(self):
        """Bind mathematical decisions and linked runs to the same catalog and checker.

        @return ContinuationWorkspace over the existing feedback and derivation modules.
        """
        return ContinuationWorkspace(FeedbackWorkspace(self._reasoning()))

    def do_GET(self):
        """Serve the workbench, verified pages, history and frozen exports."""
        try:
            self._guard()
            # URL values are identifiers and page ranges, never local filesystem paths.
            url = urlsplit(self.path)
            route, query = url.path, {key: values[0] for key, values in parse_qs(url.query).items()}
            workspace = self.server.workspace
            assets = {"/msa": ("msa.html", "text/html; charset=utf-8"),
                      "/msa.js": ("msa.js", "text/javascript; charset=utf-8"),
                      "/msa.css": ("msa.css", "text/css; charset=utf-8"),
                      "/compare": ("comparison.html", "text/html; charset=utf-8"),
                      "/comparison.js": ("comparison.js", "text/javascript; charset=utf-8"),
                      "/comparison.css": ("comparison.css", "text/css; charset=utf-8"),
                      "/reasoning": ("reasoning.html", "text/html; charset=utf-8"),
                      "/reasoning.js": ("reasoning.js", "text/javascript; charset=utf-8"),
                      "/feedback.js": ("feedback.js", "text/javascript; charset=utf-8"),
                      "/continuation.js": ("continuation.js", "text/javascript; charset=utf-8"),
                      "/reasoning.css": ("reasoning.css", "text/css; charset=utf-8"),
                      "/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if route in assets:
                name, mime = assets[route]
                self._send(200, (self.server.assets / name).read_bytes(), mime)
            elif route == "/api/msa/catalog":
                self._send(200,{"projects":self.server.msa.catalog(),"token":self.server.token,"testing":self.server.testing,
                    "capabilities":CAPABILITIES,"model":json.loads((self.server.assets.parent/"configs/model-service.json").read_bytes())})
            elif route == "/api/msa/project":
                self._send(200,self.server.msa.read(query["id"],query.get("revision")))
            elif route == "/api/msa/export":
                self._send(200,self.server.msa.export(query["id"],query.get("revision")),filename="msa.json")
            elif route == "/api/msa/example":
                require(query["name"] in ("execution-budget","prosa-ceil"),"unknown_example","找不到示例。")
                self._send(200,json.loads((self.server.assets.parent/"examples/msa"/(query["name"]+".json")).read_bytes()))
            elif route == "/api/msa/frozen":
                self._send(200,self.server.msa.frozen(query["id"]))
            elif route == "/api/msa/results":
                self._send(200,self.server.msa.results(query["freeze"]))
            elif route == "/api/msa/result":
                self._send(200,self.server.msa.result(query["id"]))
            elif route == "/api/msa/artifact":
                self._send(200,self.server.msa.artifact(query["result"],query["digest"]),"text/plain; charset=utf-8")
            elif route == "/api/catalog":
                self._send(200, {**workspace.catalog(), "token": self.server.token, "testing": self.server.testing})
            elif route == "/api/project":
                self._send(200, workspace.read(query["id"], query.get("revision")))
            elif route == "/api/comparison-options":
                self._send(200,ComparisonWorkspace(self._reasoning()).options(query["child"]))
            elif route == "/api/comparison":
                self._send(200,ComparisonWorkspace(self._reasoning()).read(query["id"]))
            elif route == "/api/proposal-review":
                self._send(200,self._continuation().review(query["id"]))
            elif route == "/api/linked-runs":
                self._send(200,self._continuation().history(query["run"]))
            elif route == "/api/proposal":
                self._send(200,FeedbackWorkspace(self._reasoning()).read(query["id"]))
            elif route == "/api/feedback":
                self._send(200,FeedbackWorkspace(self._reasoning()).history(query["run"]))
            elif route == "/api/derivation":
                self._send(200,self._reasoning().read(query["id"],query.get("selection")))
            elif route == "/api/derivations":
                self._send(200,self._reasoning().history(query["mapping"]))
            elif route == "/api/derivation-evidence":
                self._send(200,self._reasoning().evidence(query["run"],query["attempt"]))
            elif route == "/api/mappings":
                self._send(200, FormalMapping(workspace, self.server.assets.parent).history(query["freeze"]))
            elif route == "/api/mapping":
                self._send(200, FormalMapping(workspace, self.server.assets.parent).open(query["id"]))
            elif route == "/api/frozen":
                result = workspace.frozen(query["id"])
                self._send(200, result, filename=("context-" + result["id"][:12] + ".json") if "download" in query else None)
            elif route in ("/api/page", "/api/image"):
                extraction_id, number = query["extraction"], int(query["page"])
                layout = workspace.importer.open(extraction_id)
                require(1 <= number <= len(layout.pages), "invalid_page", "页码超出论文范围")
                page = layout.pages[number - 1]
                if route == "/api/page":
                    self._send(200, {"number": number, "count": len(layout.pages), "width": page.width,
                                     "height": page.height, "text": page.text,"issues":[asdict(issue) for issue in layout.issues if issue.page in (None,number)]})
                else:
                    key = (extraction_id, number)
                    if key not in self.server.images:
                        if len(self.server.images) >= 20:
                            self.server.images.clear()
                        # @var renderer Preserve the parser/renderer profile recorded by this extraction.
                        renderer = PaperImporter(workspace.ledger,MsaPoppler()) if layout.profile["name"]=="msa-poppler-bbox-layout" else workspace.importer
                        self.server.images[key] = renderer.render(extraction_id,number)
                    self._send(200, self.server.images[key], "image/png")
            elif route == "/api/reference":
                located = workspace.importer.locate(query["extraction"], int(query["page"]),
                                                    int(query["start"]), int(query["end"]))
                self._send(200, asdict(located))
            else:
                self._send(404, {"code": "unknown_route", "message": "页面不存在"})
        except Exception as error:
            self._error(error)

    def _checkpoint(self):
        """Publish current data before acknowledging a mutation.

        @raise ReviewFailure If publication fails; subsequent writes retry it first.
        """
        try:
            self.server.checkpoint()
            self.server.persistence_failed = False
        except Exception:
            self.server.persistence_failed = True
            raise ReviewFailure("checkpoint_failed", "操作可能已写入运行中的数据库，但备份发布失败。"
                                "请保留服务进程并重试，成功前不要关闭工作台。") from None

    def do_POST(self):
        """Execute a bounded same-origin operation and durably publish mutations."""
        try:
            self._guard(write=True)
            # Bound length before reading; chunked uploads are not supported.
            length = int(self.headers.get("Content-Length", "-1"))
            route = urlsplit(self.path).path
            limit = 20 * 1024 * 1024 if route in ("/api/import","/api/msa/pdf") else 2 * 1024 * 1024
            require(self.headers.get("Transfer-Encoding") is None and 0 < length <= limit,
                    "invalid_request", "请求为空或超过大小限制")
            data = self.rfile.read(length)
            require(len(data) == length, "invalid_request", "请求内容未完整到达")
            if self.server.persistence_failed:
                self._checkpoint()
            workspace = self.server.workspace
            mutable = route in ("/api/msa/create","/api/msa/commit","/api/msa/freeze","/api/msa/map","/api/msa/prove","/api/msa/pdf","/api/import", "/api/projects", "/api/commit", "/api/freeze", "/api/map", "/api/derive", "/api/select-route", "/api/feedback", "/api/proposal-decision", "/api/adopt-proposal", "/api/comparisons")
            try:
                if route in ("/api/import","/api/msa/pdf"):
                    require(self.headers.get("Content-Type") == "application/pdf", "invalid_request", "请选择 PDF 文件")
                    name = Path(unquote(self.headers.get("X-Filename", "paper.pdf"))).name[:120] or "paper.pdf"
                    with TemporaryDirectory(prefix="autorta-upload-") as temp:
                        path = Path(temp) / "source.pdf"
                        path.write_bytes(data)
                        # @var importer Generic PDF handling has its own versioned parser policy.
                        importer = PaperImporter(workspace.ledger,MsaPoppler()) if route=="/api/msa/pdf" else workspace.importer
                        extraction_id = importer.import_pdf(path)
                    if route=="/api/msa/pdf":
                        result = self.server.msa.from_pdf(extraction_id,name,"local user")
                    else:
                        semantic_id = workspace.semantics.extract(extraction_id)
                        result = workspace.create(semantic_id,name)
                else:
                    require(self.headers.get("Content-Type", "").split(";")[0] == "application/json",
                            "invalid_request", "请求格式应为 JSON")
                    body = json.loads(data)
                    require(isinstance(body, dict), "invalid_request", "请求应为字段对象")
                    if route == "/api/stop":
                        require(body == {}, "invalid_request", "停止请求不接受附加字段")
                        self._checkpoint()
                        self._send(200, {"stopping": True})
                        Thread(target=self.server.shutdown, daemon=True).start()
                        return
                    # A mapping receipt is separate from the immutable review freeze and proof outcomes.
                    mapper = FormalMapping(workspace, self.server.assets.parent)
                    reasoning = self._reasoning()
                    continuation = self._continuation()
                    # @var msa Source-independent operations use the same origin checks and checkpoint boundary.
                    msa = self.server.msa
                    operations = {
                        "/api/msa/create":(msa.create,("name","document","actor")),
                        "/api/msa/preview":(msa.preview,("project","expected","document")),
                        "/api/msa/commit":(msa.commit,("project","expected","document","preview","actor","reason")),
                        "/api/msa/freeze":(msa.freeze,("project","expected","actor","reason")),
                        "/api/msa/map":(msa.map,("freeze",)),
                        "/api/msa/prove":(msa.prove,("mapping","max_checks")),
                        "/api/msa/expression":(parse_expression,("source",)),
                        "/api/comparisons": (ComparisonWorkspace(reasoning).create, ("parent","child","parent_selection","child_selection")),
                        "/api/proposal-decision": (continuation.decide, ("proposal","preview","expected","choice","actor","reason")),
                        "/api/adopt-proposal": (continuation.adopt, ("proposal","preview","decision","budget","actor","request_id")),
                        "/api/feedback": (FeedbackWorkspace(reasoning).submit, ("run","selection","target","text","actor","intent")),
                        "/api/derive": (reasoning.derive, ("mapping",)),
                        "/api/select-route": (reasoning.select, ("run","expected","choices")),
                        "/api/map-preview": (mapper.prepare, ("freeze",)),
                        "/api/map": (mapper.compile, ("freeze",)),
                        "/api/projects": (workspace.create, ("semantic_id", "name")),
                        "/api/preview": (workspace.prepare, ("project", "expected", "patch")),
                        "/api/commit": (workspace.commit, ("project", "expected", "patch", "token", "actor", "reason")),
                        "/api/freeze-preview": (workspace.preview_freeze, ("project", "expected")),
                        "/api/freeze": (workspace.freeze, ("project", "expected", "token", "actor")),
                    }
                    require(route in operations, "unknown_route", "操作不存在")
                    operation, fields = operations[route]
                    require(set(body) == set(fields), "invalid_request", "请求字段缺失或包含多余字段")
                    result = operation(**body)
            finally:
                # Save even a partially completed import; no successful response precedes publication.
                if mutable:
                    self._checkpoint()
            self._send(200, result)
        except Exception as error:
            self._error(error)
