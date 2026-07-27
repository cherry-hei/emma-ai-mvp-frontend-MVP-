# AWS deploy — moved

This file used to document deploying the Emma AI API to **AWS App Runner**. That
guide is obsolete: **AWS closed App Runner to new customers** (maintenance mode
from 30 Apr 2026), so a new AWS account can no longer create App Runner services.
AWS's recommended replacement is **Amazon ECS Express Mode**.

The current, canonical guide is **[`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md)**
— ECR + ECS Express Mode + GitHub Actions auto-deploy.

Full deployment sequence:

1. [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md) — database (Supabase Cloud)
2. [`SETUP_BACKEND_AWS.md`](SETUP_BACKEND_AWS.md) — API (ECS Express Mode)
3. [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md) — UI (Amplify Hosting)

The auto-deploy workflow lives at
[`.github/workflows/deploy-api.yml`](.github/workflows/deploy-api.yml).
