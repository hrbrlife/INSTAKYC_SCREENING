import fs from 'fs';
import path from 'path';

const dir = process.argv[2] || '/tmp/webshot';
const cutoff = Date.now() - 5 * 60 * 1000; // 5 minutes

if (fs.existsSync(dir)) {
  for (const file of fs.readdirSync(dir)) {
    const fp = path.join(dir, file);
    const stat = fs.statSync(fp);
    if (stat.mtimeMs < cutoff) {
      fs.unlinkSync(fp);
    }
  }
}
