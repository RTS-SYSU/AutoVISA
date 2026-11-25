/**
 * Serve the local AutoVISA workspace and its same-origin model connection.
 * @example node tools/serve-prototype.cjs --port 8769
 */
const http = require("node:http");
const {serveOpenAI} = require("./openai-service.cjs");
/** @type {typeof import('node:fs')} Stream the workspace document to the local browser. */
const fs = require("node:fs");
/** @type {typeof import('node:path')} Paths are resolved relative to this launcher. */
const path = require("node:path");
/** @type {string} Web directory shared by the standalone prototype files. */
const root = path.resolve(__dirname, "../web");
/** @type {number} Optional local port, independent from the existing backend. */
const port = Number(process.argv[process.argv.indexOf("--port") + 1]) || 8769;
/**
 * Map a request to a prototype resource, keeping the rest of the repository private.
 * @param {import('node:http').IncomingMessage} request Local browser request.
 * @param {import('node:http').ServerResponse} response Streaming HTTP response.
 */
function serve(request, response) {
  /** @type {string} URL path without query parameters. */
  const route = new URL(request.url, "http://localhost").pathname;
  if(route.startsWith("/api/openai/")){void serveOpenAI(request,response,route,port);return;}
  /** @type {Object<string,string>} Only the workspace and its local document readers are served. */
  const assets = {
    "/": "autovisa-workspace.html", "/prototype.html": "autovisa-workspace.html",
    "/autovisa-workspace.html": "autovisa-workspace.html", "/document-reader.js": "document-reader.js", "/derivation-view.js":"derivation-view.js", "/reasoning-skills.js":"reasoning-skills.js", "/evidence-ledger.js":"evidence-ledger.js", "/argument-audit.js":"argument-audit.js",
    "/vendor/pdfjs/pdf.min.mjs": "vendor/pdfjs/pdf.min.mjs",
    "/vendor/pdfjs/pdf.worker.min.mjs": "vendor/pdfjs/pdf.worker.min.mjs",
    "/vendor/ui/lucide.js":"vendor/ui/lucide.js", "/vendor/ui/katex.min.js":"vendor/ui/katex.min.js",
    "/vendor/jszip/jszip.min.js": "vendor/jszip/jszip.min.js"
  };
  if (!Object.hasOwn(assets, route)) { response.writeHead(404); response.end(); return; }
  const file = path.join(root, assets[route]);
  if (!fs.existsSync(file)) { response.writeHead(404); response.end("Not found"); return; }
  response.writeHead(200, { "Content-Type": file.endsWith(".html") ? "text/html; charset=utf-8" : "text/javascript; charset=utf-8", "Cache-Control": "no-store" });
  fs.createReadStream(file).pipe(response);
}
/** @type {import('node:http').Server} Preview lifetime is controlled by the terminal. */
const server = http.createServer(serve);
server.listen(port, "127.0.0.1", () => console.log(`AutoVISA workspace: http://127.0.0.1:${port}/`));
server.on("error", error => { console.error(error.message); process.exitCode = 1; });
