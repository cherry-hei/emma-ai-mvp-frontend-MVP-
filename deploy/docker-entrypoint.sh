#!/usr/bin/env sh
# Container entrypoint for the Emma AI Reflex dashboard on AWS App Runner.
set -eu

: "${PORT:=8080}"
: "${BACKEND_PORT:=8000}"
export PORT BACKEND_PORT

# 1) Bring the port up immediately (serving the frontend built at image-build
#    time) so the App Runner health check passes while slower steps run below.
caddy start --config /etc/caddy/Caddyfile --adapter caddyfile

# 2) Re-bake the frontend against the PUBLIC url. App Runner injects API_URL
#    (and DEPLOY_URL) as env vars; reflex reads them when exporting. Uses the
#    bun/node deps already cached in the image, so this is fast.
if [ -n "${API_URL:-}" ]; then
  echo "[entrypoint] Baking frontend for API_URL=${API_URL}"
  reflex export --frontend-only --no-zip
else
  echo "[entrypoint] WARNING: API_URL is not set."
  echo "[entrypoint] The UI will target localhost and cannot reach the backend"
  echo "[entrypoint] from a browser. Set API_URL to your App Runner URL and"
  echo "[entrypoint] redeploy — see AWS_DEPLOY.md."
fi

# 3) Start the Reflex backend in the foreground (keeps the container alive).
exec reflex run --env prod --backend-only --backend-port "${BACKEND_PORT}"
