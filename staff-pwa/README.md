# Emma AI Staff PWA

A static Vite/React staff application prepared for a private `emma-ai-staff-pwa` repository and Vercel SPA hosting. It communicates directly from the browser to the approved FastAPI backend using the signed-in user's Bearer token. It does not connect to Supabase directly and contains no service-role credential.

## Configuration

Copy `.env.example` to a local, untracked `.env.local` and set only:

```bash
VITE_API_BASE=https://approved-fastapi-origin
```

`VITE_API_BASE` is a public browser setting, not a secret. It must be one HTTPS backend origin (no path, query, fragment, or credentials); the client rejects any other value. The selected Vercel preview/production origin must be added to the backend CORS allowlist before browser login can work. Configure the value through Vercel's environment settings; do not commit it.

## Commands

```bash
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

`vercel.json` builds `dist/` and rewrites client-side routes to `index.html`. It intentionally does not add a Vercel API proxy or server runtime.

## Security and verified feature boundaries

- Authentication remains browser → FastAPI Bearer → user-bound backend/RLS. The client never bypasses FastAPI or calls Supabase.
- The session client rejects late responses after a login/logout/token-generation change, coalesces refreshes for the same credential snapshot, and clears only the still-current expired session.
- The supplied public OpenAPI 0.6.0 snapshot (reviewed 2026-10-31) defines no direct-message/chat path and no request-window path. Both functions are explicitly disabled; no fake response or speculative request is made.
- Records use the staff-scoped `/me/leave-requests` response and apply an inclusive client-side date overlap filter. The verified staff endpoint has no date-range parameters; using manager-oriented list filters would risk weakening the user-bound scope.
- This application registers no service worker. Startup removes legacy same-origin registrations and Cache Storage entries so the app does not cache authentication, API, or private staff data offline.

## Release boundary

This source is implementation-ready for the 4 November integration target, not a production acceptance. Real NGO data, Auth/storage/location/backups, CORS approval, and backend contracts still require the authorised owners' verification before any live release.
