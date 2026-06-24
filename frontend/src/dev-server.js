const http = require('http');
const fs = require('fs');
const path = require('path');

const host = '0.0.0.0';
const port = Number(process.env.PORT || 5173);
const apiTarget = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
const publicDir = path.resolve(__dirname, '../public');

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml'
};

function resolveFile(requestUrl) {
  const parsedUrl = new URL(requestUrl || '/', 'http://localhost');
  const pathname = parsedUrl.pathname === '/' ? '/index.html' : parsedUrl.pathname;
  const safePath = path.extname(pathname) ? pathname : '/index.html';
  const normalized = path.normalize(safePath).replace(/^(\.\.[/\\])+/, '');
  return path.join(publicDir, normalized);
}

function proxyApiRequest(req, res, parsedUrl) {
  const target = new URL(`${parsedUrl.pathname}${parsedUrl.search}`, apiTarget);
  const headers = { ...req.headers, host: target.host };
  delete headers.connection;

  const proxyReq = http.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      method: req.method,
      headers
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: `API proxy failed: ${error.message}` }));
  });

  req.pipe(proxyReq);
}

function serveStaticFile(req, res) {
  const filePath = resolveFile(req.url || '/');
  const ext = path.extname(filePath).toLowerCase();

  if (!filePath.startsWith(publicDir)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(filePath, (error, content) => {
    if (error) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }

    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    res.end(content);
  });
}

const server = http.createServer((req, res) => {
  const parsedUrl = new URL(req.url || '/', 'http://localhost');

  if (parsedUrl.pathname === '/favicon.ico') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (parsedUrl.pathname === '/api' || parsedUrl.pathname.startsWith('/api/')) {
    proxyApiRequest(req, res, parsedUrl);
    return;
  }

  serveStaticFile(req, res);
});

server.listen(port, host, () => {
  console.log(`Frontend running at http://localhost:${port}`);
  console.log(`API proxy target: ${apiTarget}`);
});
