# puppeteer_srv

A minimal HTTP service intended to back the open-web adverse-media search component.

- Requires environment variables `PUPPETEER_HEADLESS` and `REDIS_URL` to start.
- Writes temporary artefacts to `/tmp/webshot` (configurable via `WEBSHOT_DIR`).
- Includes a `cleanup` script to purge artefacts older than five minutes.
- `npm run rotate` is a placeholder for proxy rotation logic.
