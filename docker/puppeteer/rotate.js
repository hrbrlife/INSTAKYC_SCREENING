import fs from 'fs';
import path from 'path';

const userAgentCandidates = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
];

const targetFile = process.env.USER_AGENT_FILE || path.join(process.env.WEBSHOT_DIR || '/tmp/webshot', 'user-agent.txt');
const nextAgent = userAgentCandidates[Math.floor(Math.random() * userAgentCandidates.length)];

fs.mkdirSync(path.dirname(targetFile), { recursive: true });
fs.writeFileSync(targetFile, `${nextAgent}\n`, 'utf8');

console.log(`User agent rotated -> ${nextAgent}`);
