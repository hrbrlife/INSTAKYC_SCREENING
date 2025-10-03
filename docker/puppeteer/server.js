import express from 'express';
import http from 'http';
import fs from 'fs';
import path from 'path';
import * as BullMQ from 'bullmq';
import { randomUUID } from 'crypto';
import puppeteer from 'puppeteer';
import sanitizeHtml from 'sanitize-html';
import { collectDefaultMetrics, Counter, Histogram, Registry } from 'prom-client';

function resolveSecret(envValue, filePath) {
  if (envValue && envValue.trim()) {
    return envValue.trim();
  }
  if (filePath && filePath.trim()) {
    const resolvedPath = filePath.trim();
    try {
      return fs.readFileSync(resolvedPath, 'utf8').trim();
    } catch (err) {
      throw new Error(`Secret file ${resolvedPath} is not accessible`);
    }
  }
  return undefined;
}

const redisUrl = resolveSecret(process.env.REDIS_URL, process.env.REDIS_URL_FILE) || 'redis://127.0.0.1:6379';
const queueName = process.env.MEDIA_QUEUE_NAME || 'adverse-media-search';
const headlessInput = (process.env.PUPPETEER_HEADLESS ?? 'true').toLowerCase();
const headless = headlessInput !== 'false';
const screenshotDir = process.env.WEBSHOT_DIR || '/tmp/webshot';
const concurrency = parseInt(process.env.SCRAPE_CONCURRENCY || '2', 10);
const maxAttempts = parseInt(process.env.SCRAPE_MAX_ATTEMPTS || '3', 10);
const navigationTimeout = parseInt(process.env.NAVIGATION_TIMEOUT_MS || '20000', 10);
const retentionHours = parseInt(process.env.ARTIFACT_RETENTION_HOURS || '24', 10);
const defaultMaxArticles = parseInt(process.env.DEFAULT_MAX_ARTICLES || '5', 10);
const userAgentFile = process.env.USER_AGENT_FILE || path.join(screenshotDir, 'user-agent.txt');
const fakeMode = process.env.PUPPETEER_FAKE_MODE === '1';
const defaultServiceToken = 'change_me_worker';
const serviceToken = resolveSecret(process.env.SERVICE_TOKEN ?? defaultServiceToken, process.env.SERVICE_TOKEN_FILE);
const serviceTokenHeader = process.env.SERVICE_TOKEN_HEADER || 'X-Service-Token';
const allowAuthorizationHeader = (process.env.SERVICE_TOKEN_ALLOW_AUTHORIZATION || 'true').toLowerCase() === 'true';

fs.mkdirSync(screenshotDir, { recursive: true });

const metricsRegistry = new Registry();
collectDefaultMetrics({ register: metricsRegistry, prefix: 'adverse_media_' });

const httpRequestsTotal = new Counter({
  name: 'adverse_media_http_requests_total',
  help: 'Total HTTP requests processed by the adverse media service',
  labelNames: ['method', 'route', 'status_code'],
  registers: [metricsRegistry]
});

const httpRequestDurationSeconds = new Histogram({
  name: 'adverse_media_http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route'],
  buckets: [0.05, 0.1, 0.25, 0.5, 1, 2, 5],
  registers: [metricsRegistry]
});

const sanitizeConfig = {
  allowedTags: sanitizeHtml.defaults.allowedTags.concat([
    'img',
    'figure',
    'figcaption',
    'picture',
    'source',
    'header',
    'footer',
    'section',
    'article'
  ]),
  allowedAttributes: {
    '*': ['class', 'id', 'lang', 'data-*'],
    a: ['href', 'name', 'target', 'rel'],
    img: ['src', 'srcset', 'alt'],
    source: ['srcset', 'type', 'media']
  },
  allowedSchemes: ['http', 'https', 'data', 'mailto']
};

function safeJobKey(jobId) {
  return jobId.toString().replace(/[^a-zA-Z0-9_-]/g, '_');
}

function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function readUserAgent() {
  try {
    const ua = fs.readFileSync(userAgentFile, 'utf8').trim();
    if (ua) {
      return ua;
    }
  } catch (_) {
    // ignore missing user agent file
  }
  return 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
}

let browserPromise;
async function getBrowser() {
  if (browserPromise) {
    const existing = await browserPromise;
    if (existing.isConnected()) {
      return existing;
    }
  }
  browserPromise = puppeteer
    .launch({
      headless: headless ? 'new' : false,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    })
    .then((browser) => {
      browser.on('disconnected', () => {
        browserPromise = undefined;
      });
      return browser;
    });
  return browserPromise;
}

async function captureSearch(job) {
  const { query, locale = 'en-US', maxArticles = defaultMaxArticles } = job.data;
  if (!query || !query.trim()) {
    throw new Error('A non-empty query is required');
  }
  const normalizedQuery = query.trim();
  const key = safeJobKey(job.id);
  const jobDir = path.join(screenshotDir, key);
  fs.mkdirSync(jobDir, { recursive: true });
  const htmlFile = path.join(jobDir, 'page.html');
  const screenshotFile = path.join(jobDir, 'screenshot.png');
  const summaryFile = path.join(jobDir, 'summary.json');
  let searchUrl = `https://news.google.com/search?q=${encodeURIComponent(normalizedQuery)}&hl=${encodeURIComponent(locale)}&gl=${encodeURIComponent(locale.split('-')[1] || 'US')}&ceid=${encodeURIComponent(locale.replace('-', ':'))}`;
  let articles;

  if (fakeMode) {
    articles = [
      {
        title: `Placeholder headline for ${normalizedQuery}`,
        url: 'https://example.com/adverse-media-placeholder',
        source: 'example.com'
      }
    ];
    const fakeHtml = `<html><body><main><h1>${escapeHtml(
      normalizedQuery
    )}</h1><p>Placeholder adverse media result.</p></main></body></html>`;
    const sanitizedHtml = sanitizeHtml(fakeHtml, sanitizeConfig);
    fs.writeFileSync(htmlFile, sanitizedHtml, 'utf8');
    const pngBuffer = Buffer.from(
      '89504E470D0A1A0A0000000D49484452000000010000000108020000009077253D0000000A49444154789C636000000200010000FFFF030000000049454E44AE426082',
      'hex'
    );
    fs.writeFileSync(screenshotFile, pngBuffer);
  } else {
    const browser = await getBrowser();
    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(navigationTimeout);
    const userAgent = readUserAgent();
    await page.setUserAgent(userAgent);
    try {
      await page.goto(searchUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('article', { timeout: navigationTimeout }).catch(() => {});
      await page.waitForTimeout(1500);
      articles = await page.evaluate((limit) => {
        const nodes = Array.from(document.querySelectorAll('article h3 a'));
        return nodes.slice(0, limit).map((node) => ({
          title: node.textContent?.trim() || '',
          url: node.href,
          source: node.closest('article')?.querySelector('a[href^="https://news.google.com/rss/articles"], a[aria-label]')?.textContent?.trim() || undefined
        }));
      }, maxArticles);

      const rawHtml = await page.content();
      const sanitizedHtml = sanitizeHtml(rawHtml, sanitizeConfig);
      fs.writeFileSync(htmlFile, sanitizedHtml, 'utf8');
      await page.screenshot({ path: screenshotFile, fullPage: true });
    } finally {
      await page.close();
    }
  }

  const now = new Date();
  const retentionUntil = new Date(now.getTime() + retentionHours * 60 * 60 * 1000);
  const summary = {
    id: job.id,
    query: normalizedQuery,
    locale,
    searchUrl,
    fetchedAt: now.toISOString(),
    retentionExpiresAt: retentionUntil.toISOString(),
    metadata: job.data.metadata || {},
    articles,
    artifacts: {
      html: path.relative(screenshotDir, htmlFile),
      screenshot: path.relative(screenshotDir, screenshotFile),
      summary: path.relative(screenshotDir, summaryFile)
    }
  };
  fs.writeFileSync(summaryFile, JSON.stringify(summary, null, 2), 'utf8');
  return summary;
}

const connectionOptions = {
  connection: {
    url: redisUrl,
    maxRetriesPerRequest: null
  }
};

function createMemoryDriver(processor) {
  const jobs = new Map();

  class MemoryJob {
    constructor(id, data) {
      this.id = id;
      this.data = data;
      this.timestamp = Date.now();
      this.returnvalue = undefined;
      this.failedReason = undefined;
      this.stacktrace = [];
      this.attemptsMade = 0;
      this.state = 'waiting';
    }

    async getState() {
      return this.state;
    }
  }

  async function run(job) {
    job.state = 'active';
    job.attemptsMade += 1;
    try {
      job.returnvalue = await processor(job);
      job.state = 'completed';
    } catch (err) {
      job.failedReason = err.message;
      job.stacktrace = err.stack ? [err.stack] : [];
      job.state = 'failed';
    }
  }

  const queue = {
    client: Promise.resolve({ ping: async () => 'PONG' }),
    async add(_name, data) {
      const id = randomUUID();
      const job = new MemoryJob(id, data);
      jobs.set(id, job);
      setImmediate(() => {
        run(job).catch(() => {});
      });
      return job;
    },
    async getJob(id) {
      return jobs.get(id) || null;
    },
    async close() {}
  };

  const worker = {
    async waitUntilReady() {},
    async close() {}
  };

  const scheduler = {
    async waitUntilReady() {},
    async close() {}
  };

  return { queue, worker, scheduler };
}

const useMemoryQueue = redisUrl.startsWith('memory://');

let queue;
let scheduler;
let worker;

if (useMemoryQueue) {
  const memoryDriver = createMemoryDriver(captureSearch);
  queue = memoryDriver.queue;
  scheduler = memoryDriver.scheduler;
  worker = memoryDriver.worker;
} else {
  queue = new BullMQ.Queue(queueName, {
    ...connectionOptions,
    defaultJobOptions: {
      attempts: maxAttempts,
      backoff: { type: 'exponential', delay: 3000 }
    }
  });
  scheduler = new BullMQ.QueueScheduler(queueName, connectionOptions);
  worker = new BullMQ.Worker(queueName, captureSearch, {
    ...connectionOptions,
    concurrency
  });
}

let ready = useMemoryQueue;

const readiness = useMemoryQueue
  ? Promise.resolve()
  : Promise.all([scheduler.waitUntilReady(), worker.waitUntilReady()]);

readiness
  .then(() => {
    ready = true;
    console.log(
      `Adverse media worker ready (queue: ${queueName}, concurrency: ${concurrency}, driver: ${
        useMemoryQueue ? 'memory' : 'redis'
      })`
    );
  })
  .catch((err) => {
    console.error('Failed to initialise worker', err);
    process.exit(1);
  });

const app = express();
app.use(express.json({ limit: '32kb' }));

app.use((req, res, next) => {
  const end = httpRequestDurationSeconds.startTimer({ method: req.method, route: req.path });
  res.on('finish', () => {
    const route = req.route?.path || req.path;
    httpRequestsTotal.labels(req.method, route, String(res.statusCode)).inc();
    end({ method: req.method, route });
  });
  next();
});

app.use((req, res, next) => {
  if (!serviceToken) {
    return next();
  }
  const headerValue = req.get(serviceTokenHeader);
  let candidate = headerValue ? headerValue.trim() : '';
  if (!candidate && allowAuthorizationHeader) {
    const authHeader = req.get('authorization');
    if (authHeader) {
      const value = authHeader.trim();
      candidate = value.toLowerCase().startsWith('bearer ') ? value.slice(7).trim() : value;
    }
  }
  if (!candidate) {
    return res.status(401).json({ error: 'missing service token' });
  }
  if (candidate !== serviceToken) {
    return res.status(403).json({ error: 'invalid service token' });
  }
  return next();
});

app.get('/healthz', async (_req, res) => {
  if (!ready) {
    return res.status(503).json({ status: 'initialising' });
  }
  try {
    const client = await queue.client;
    await client.ping();
    return res.json({ status: 'ok' });
  } catch (err) {
    return res.status(503).json({ status: 'error', error: err.message });
  }
});

app.post('/tasks', async (req, res) => {
  const { query, locale, maxArticles, metadata } = req.body || {};
  if (!query || typeof query !== 'string' || !query.trim()) {
    return res.status(400).json({ error: 'query is required' });
  }
  const job = await queue.add('adverse-media-search', {
    query,
    locale: locale || 'en-US',
    maxArticles: typeof maxArticles === 'number' ? Math.max(1, Math.min(maxArticles, 20)) : defaultMaxArticles,
    metadata: metadata || {}
  }, {
    removeOnComplete: false,
    removeOnFail: false
  });
  res.status(202).json({ id: job.id, state: 'queued' });
});

app.get('/tasks/:id', async (req, res) => {
  const job = await queue.getJob(req.params.id);
  if (!job) {
    return res.status(404).json({ error: 'job not found' });
  }
  const state = await job.getState();
  const response = {
    id: job.id,
    state,
    attemptsMade: job.attemptsMade,
    failedReason: job.failedReason,
    stacktrace: job.stacktrace,
    queuedAt: new Date(job.timestamp).toISOString(),
    data: job.data
  };
  if (state === 'completed') {
    response.result = job.returnvalue;
  }
  res.json(response);
});

const artifactFiles = {
  html: 'page.html',
  screenshot: 'screenshot.png',
  summary: 'summary.json'
};

app.get('/tasks/:id/artifacts/:type', (req, res) => {
  const fileName = artifactFiles[req.params.type];
  if (!fileName) {
    return res.status(404).json({ error: 'unknown artifact' });
  }
  const safeKey = safeJobKey(req.params.id);
  const filePath = path.join(screenshotDir, safeKey, fileName);
  if (!filePath.startsWith(path.join(screenshotDir, safeKey))) {
    return res.status(400).json({ error: 'invalid path' });
  }
  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: 'artifact not found' });
  }
  const typeMap = {
    html: 'text/html',
    screenshot: 'image/png',
    summary: 'application/json'
  };
  res.setHeader('Content-Type', typeMap[req.params.type] || 'application/octet-stream');
  res.sendFile(filePath);
});

app.get('/metrics', async (_req, res) => {
  const payload = await metricsRegistry.metrics();
  res.setHeader('Content-Type', metricsRegistry.contentType);
  res.send(payload);
});

const server = http.createServer(app);
const port = process.env.PORT || 7000;
server.listen(port, () => {
  console.log(`Adverse media service listening on ${port}`);
});

async function shutdown() {
  console.log('Shutting down adverse media service');
  await Promise.allSettled([
    worker.close(),
    scheduler.close(),
    queue.close()
  ]);
  if (browserPromise) {
    const browser = await browserPromise;
    await browser.close();
  }
  server.close(() => process.exit(0));
}

process.on('SIGTERM', () => {
  shutdown();
});

process.on('SIGINT', () => {
  shutdown();
});
