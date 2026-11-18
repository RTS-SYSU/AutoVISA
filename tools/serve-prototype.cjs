/**
 * Serve only the isolated prototype files over loopback; no application APIs exist.
 * @example node tools/serve-prototype.cjs --port 8769
 */
const http = require("node:http");
/** @type {typeof import('node:fs')} File streaming keeps PDF previews inexpensive. */
const fs = require("node:fs");
/** @type {typeof import('node:path')} Paths are resolved relative to this launcher. */
const path = require("node:path");
/** @type {string} Web directory shared by the standalone prototype files. */
const root = path.resolve(__dirname, "../web");
/** @type {number} Optional local port, independent from the existing backend. */
const port = Number(process.argv[process.argv.indexOf("--port") + 1]) || 8769;
/** @type {Record<string,string>} Explicit MIME types for the buildless prototype. */
const types = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".png": "image/png", ".pdf": "application/pdf" };
/**
 * Map a request to a prototype resource, keeping the rest of the repository private.
 * @param {import('node:http').IncomingMessage} request Local browser request.
 * @param {import('node:http').ServerResponse} response Streaming HTTP response.
 */
function serve(request, response) {
  /** @type {string} URL path without query parameters. */
  const route = new URL(request.url, "http://localhost").pathname;
  /** @type {string} Root opens the prototype while all other paths remain explicit. */
  const relative = route === "/" ? "autovisa-workspace.html" : route.slice(1);
  if (!/^(autovisa-workspace\.html|prototype\.(html|css|js)|prototype-assets\/(case11-page[24]\.png|case11\.pdf))$/.test(relative)) {
    response.writeHead(404); response.end("Not found"); return;
  }
  /** @type {string} An allowlisted, existing resource inside the web directory. */
  const file = path.join(root, relative);
  if (!fs.existsSync(file)) { response.writeHead(404); response.end("Not found"); return; }
  response.writeHead(200, { "Content-Type": types[path.extname(file)], "Cache-Control": "no-store" });
  fs.createReadStream(file).pipe(response);
}
/** @type {import('node:http').Server} Preview lifetime is controlled by the terminal. */
const server = http.createServer(serve);
server.listen(port, "127.0.0.1", () => console.log(`AutoVISA workspace: http://127.0.0.1:${port}/`));
server.on("error", error => { console.error(error.message); process.exitCode = 1; });
