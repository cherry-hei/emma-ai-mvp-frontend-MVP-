# Emma AI

Intelligent nurse / care-worker **rostering** for HK residential care homes. This
repository is a monorepo containing two apps that run together:

| App | Path | Stack | Local URL |
|---|---|---|---|
| **Frontend** | repo root (`src/`) | Next.js 16 (Turbopack) · React 19 · Tailwind v4 · shadcn/radix | http://localhost:3001 |
| **Backend** | [`emma-ai-app/`](emma-ai-app) | FastAPI · Supabase (Postgres + GoTrue + RLS) · OR-Tools CP-SAT solver | http://localhost:8000 (docs at `/docs`) |

The frontend consumes the backend's REST API and codegens its typed client from
`http://localhost:8000/openapi.json`. See [`emma-ai-app/README.md`](emma-ai-app/README.md)
and [`emma-ai-app/RUNBOOK.md`](emma-ai-app/RUNBOOK.md) for backend details.

## Getting started

### One command (Windows) — runs both apps

```bash
dev.cmd
```

`dev.cmd` installs frontend deps on first run, then launches the FastAPI backend
(`uvicorn`) and the Next.js dev server in separate terminals.

### Manual

Frontend (repo root):

```bash
npm install
npm run dev
```

Backend — see [`emma-ai-app/RUNBOOK.md`](emma-ai-app/RUNBOOK.md) for the full setup:

```bash
cd emma-ai-app
pip install -r requirements.txt
uvicorn api.main:app --reload
```

## Configuration

Frontend env lives in `.env.local` (gitignored):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the backend API (default `http://localhost:8000`) |
| `NEXT_PUBLIC_DEV_EMAIL` / `NEXT_PUBLIC_DEV_PASSWORD` | **Local-dev only** auto-login against a seeded account. Do not use in production — build a real login UI on `api.login()`. |

Backend env lives in `emma-ai-app/.env` (see `emma-ai-app/.env.example`).

## Frontend layout

```
src/app/        routes: dashboard, roster, staff, staff-app, compliance,
                approval, alert, personnel, reports, roi, + /api route handlers
src/components/  ui/ (shadcn), layout/, modals/, roster/
src/lib/         api.ts (typed client), apiTypes.ts, data.ts, types.ts, utils.ts
```

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Next.js dev server on port 3001 (Turbopack) |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint |

## Deployment

Containerized via [`Dockerfile`](Dockerfile); see [`AWS_DEPLOY.md`](AWS_DEPLOY.md)
for the AWS deployment guide.
