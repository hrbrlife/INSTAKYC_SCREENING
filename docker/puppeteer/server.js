import http from 'http';
import url from 'url';
import fs from 'fs';
import path from 'path';
import { randomUUID } from 'crypto';

const headless = process.env.PUPPETEER_HEADLESS;
const redisUrl = process.env.REDIS_URL;
if (!headless || !redisUrl) {
  throw new Error('Missing PUPPETEER_HEADLESS or REDIS_URL');
}

const SCREENSHOT_DIR = process.env.WEBSHOT_DIR || '/tmp/webshot';
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url, true);
  if (req.method === 'GET' && parsed.pathname === '/search') {
    const q = parsed.query.q || '';
    const filePath = path.join(SCREENSHOT_DIR, `${randomUUID()}.txt`);
    fs.writeFileSync(filePath, `query: ${q}\n`);
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ articles: [], query: q }));
  } else {
    res.statusCode = 404;
    res.end();
  }
});

const port = process.env.PORT || 7000;
server.listen(port, () => {
  console.log(`puppeteer_srv listening on ${port}`);
});
