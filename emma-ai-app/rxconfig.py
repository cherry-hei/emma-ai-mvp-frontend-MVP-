import os

import reflex as rx

# `api_url` is the origin the browser uses to reach the backend (websocket
# /_event, uploads, ping). Reflex bakes it into the frontend bundle at
# export/build time, so it must be set BEFORE the build — the API_URL env var
# alone is not read automatically. In production the app runs behind a
# single-origin reverse proxy (Caddy) on App Runner, so API_URL is set to the
# public https URL. Unset locally -> Reflex default (http://localhost:8000).
config = rx.Config(
    app_name="emma_web",
    api_url=os.environ.get("API_URL", "http://localhost:8000"),
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)
