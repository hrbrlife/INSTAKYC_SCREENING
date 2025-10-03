import fs from 'fs';
import path from 'path';

const rootDir = process.argv[2] || process.env.WEBSHOT_DIR || '/tmp/webshot';
const retentionHours = parseInt(process.env.ARTIFACT_RETENTION_HOURS || '24', 10);
const cutoff = Date.now() - retentionHours * 60 * 60 * 1000;

function prune(dir) {
  if (!fs.existsSync(dir)) {
    return;
  }
  for (const entry of fs.readdirSync(dir)) {
    const entryPath = path.join(dir, entry);
    const stat = fs.statSync(entryPath);
    if (stat.isDirectory()) {
      if (stat.mtimeMs < cutoff) {
        fs.rmSync(entryPath, { recursive: true, force: true });
      } else {
        prune(entryPath);
        const remaining = fs.existsSync(entryPath) ? fs.readdirSync(entryPath) : [];
        if (remaining.length === 0) {
          fs.rmSync(entryPath, { recursive: true, force: true });
        }
      }
    } else if (stat.mtimeMs < cutoff) {
      fs.rmSync(entryPath, { force: true });
    }
  }
}

prune(rootDir);
