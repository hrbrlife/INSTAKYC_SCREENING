# Secret management templates

The files in this directory provide **development defaults** for Docker secrets
used by the Compose stack. Replace them with environment-specific values before
running in shared environments:

- `api_gateway_keys.example` – JSON map of API keys to authorised scopes.
- `redis_url.example` – Connection string including the Redis password.
- `redis_password.example` – Password injected into the Redis container.
- `puppeteer_service_token.example` – Token required by the adverse media worker.

To supply custom secrets, copy each file without the `.example` suffix and point
Docker Compose at the new paths:

```sh
cp secrets/api_gateway_keys.example secrets/api_gateway_keys.prod
cp secrets/redis_url.example secrets/redis_url.prod
cp secrets/redis_password.example secrets/redis_password.prod
cp secrets/puppeteer_service_token.example secrets/puppeteer_service_token.prod
```

Then update `compose-sanctions.yml` or use an override file to reference the new
secret paths. Never commit environment-specific secrets to version control.
