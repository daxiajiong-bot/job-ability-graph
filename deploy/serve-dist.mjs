#!/usr/bin/env node
// Minimal static file server with /api + /health reverse proxy to the backend.
// Used by deploy/local-run.ps1 to serve the production frontend build without
// Docker/nginx. Pure Node, no external dependencies.
//
// Usage:
//   node deploy/serve-dist.mjs <distDir> [--port 5173] [--backend http://127.0.0.1:8002]

import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { createReadStream, existsSync } from "node:fs";
import { extname, join, normalize } from "node:path";

function parseArgs(argv) {
  const args = { port: 5173, backend: "http://127.0.0.1:8002", dist: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--port") args.port = Number(argv[++i]);
    else if (a === "--backend") args.backend = argv[++i];
    else if (!a.startsWith("-") && !args.dist) args.dist = a;
  }
  return args;
}

const args = parseArgs(process.argv);
if (!args.dist) {
  console.error(
    "usage: node deploy/serve-dist.mjs <distDir> [--port 5173] [--backend http://127.0.0.1:8002]"
  );
  process.exit(2);
}

const distRoot = args.dist;
const backendUrl = new URL(args.backend);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json",
};

function send(res, status, body, type = "text/plain; charset=utf-8") {
  res.writeHead(status, { "Content-Type": type });
  res.end(body);
}

function sendFile(res, filePath) {
  res.writeHead(200, {
    "Content-Type": MIME[extname(filePath).toLowerCase()] || "application/octet-stream",
  });
  const stream = createReadStream(filePath);
  stream.on("error", () => send(res, 404, "Not Found"));
  stream.pipe(res);
}

function proxy(req, res) {
  const requestFn = backendUrl.protocol === "https:" ? httpsRequest : httpRequest;
  const headers = { ...req.headers, host: backendUrl.host };
  const outbound = requestFn(
    backendUrl,
    { method: req.method, path: req.url, headers },
    (upstream) => {
      res.writeHead(upstream.statusCode, upstream.headers);
      upstream.pipe(res);
    }
  );
  outbound.on("error", (err) => send(res, 502, `Bad Gateway: ${err.message}`));
  req.pipe(outbound);
}

const server = createServer((req, res) => {
  const rawPath = (req.url || "/").split("?")[0];
  const urlPath = decodeURIComponent(rawPath);

  // Backend API + health.
  if (urlPath === "/health" || urlPath.startsWith("/health/") || urlPath.startsWith("/api")) {
    return proxy(req, res);
  }

  // Static assets, with SPA history fallback to index.html.
  let rel = normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
  let filePath = join(distRoot, rel === "/" || rel === "" ? "index.html" : rel);
  if (!existsSync(filePath)) filePath = join(distRoot, "index.html");
  if (!existsSync(filePath)) return send(res, 404, "Not Found");
  sendFile(res, filePath);
});

server.listen(args.port, "127.0.0.1", () => {
  console.log(`[serve-dist] http://127.0.0.1:${args.port}   (dist=${distRoot})`);
  console.log(`[serve-dist] /api, /health -> ${args.backend}`);
});
