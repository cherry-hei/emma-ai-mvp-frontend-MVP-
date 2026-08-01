# Setup 2 - Backend API on AWS (ECS Express Mode, auto-deploy from GitHub)

Deploy the Emma AI **REST API** (FastAPI + uvicorn + OR-Tools) to AWS, with
push-to-deploy from GitHub. End state: a public HTTPS URL like
`https://emma-ai-api.ecs.ap-southeast-1.on.aws`, redeployed automatically on
every push to the deploy branch.

**This guide is click-by-click in the AWS Console** - no AWS CLI, and no Docker
on your machine. GitHub Actions does the image build in the cloud.
(A CLI-equivalent for every step is in [Appendix - CLI equivalents](#appendix--cli-equivalents).)

**What gets deployed:** the JSON API only, from the repo-root
[`Dockerfile`](Dockerfile).
**What does NOT:** the database - that's Supabase Cloud, so do
[`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md) **first**. And the UI - see
[`SETUP_UI_AWS.md`](SETUP_UI_AWS.md).

> A live service **cannot** use your local `supabase start` database. The cloud
> DB must exist, with the schema pushed, before the API can serve anything real.

> **Why not App Runner?** AWS closed App Runner to new customers (maintenance
> mode from 30 Apr 2026); a new account can no longer create App Runner
> services. AWS's recommended replacement is **ECS Express Mode** - it
> provisions a Fargate service, Application Load Balancer, auto-scaling, HTTPS
> and a public URL, at no charge above the underlying resources. Express Mode
> deploys a **container image**, so the flow is: GitHub Actions builds the
> Dockerfile → pushes to ECR → creates/updates the Express service.

---

## Architecture

```
git push develop
      │
      ▼
GitHub Actions ──build Dockerfile──▶ Amazon ECR (image registry)
      │                                     │
      └────────deploy──────────────▶ ECS Express Mode service
                                            │  (Fargate + ALB + HTTPS + autoscale)
                                            ▼
                              https://emma-ai-api.ecs.ap-southeast-1.on.aws
                                            │
                                            ▼
                                   Supabase Cloud (Postgres)
```

You do **five things in the AWS Console** (ECR repo → 2 IAM roles → secrets →
GitHub trust), **two things in the GitHub web UI** (variables → run workflow),
and GitHub Actions creates the service itself on that first run.

---

## Before you start

1. **Supabase Cloud project ready** - schema pushed, seeded if this is `test`.
   You need four values; all four are already in your local
   `emma-ai-app/.env`, or in the Supabase dashboard:
   | Value | Where in Supabase |
   |---|---|
   | `SUPABASE_URL` | Settings → API → Project URL |
   | `SUPABASE_ANON_KEY` | Settings → API → anon / public |
   | `SUPABASE_SERVICE_ROLE_KEY` | Settings → API → service_role (**secret**) |
   | `DATABASE_URL` | Settings → Database → Connection string → URI |
2. **Your AWS account ID.** Console top-right → click your account name; the
   12-digit number is shown. Copy it - you need it repeatedly. Written
   `<ACCOUNT_ID>` below.
3. **Region set to Asia Pacific (Singapore) `ap-southeast-1`** in the top-right
   region picker. Check it on *every* console page in this guide - an
   ECR repo in the wrong region will not be found by the deploy.
4. **A default VPC** in that region. New accounts have one. Verify: **VPC**
   console → **Your VPCs** → look for one with **Default VPC = Yes**. If there
   is none: **Actions → Create default VPC**.

---

## Step 1 - Create the ECR repository

This is where built images are stored.

1. Console → search **ECR** → **Elastic Container Registry**.
2. Left nav → **Repositories** (under *Private registry*) → **Create repository**.
3. **Repository name:** `emma-ai-api`
4. Leave everything else default (private, no image scanning needed, AES-256
   encryption).
5. **Create**.

You'll land on the repository list. The **URI** column shows
`<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/emma-ai-api` - confirmation
that your account ID and region are what you think they are.

---

## Step 2 - Create the two ECS Express Mode IAM roles

Express Mode requires exactly these two role names. Create both by hand so you
know their ARNs before wiring GitHub.

### 2a. `ecsTaskExecutionRole`

1. Console → **IAM** → **Roles** → **Create role**.
2. **Trusted entity type:** *AWS service*.
3. **Service or use case:** choose **Elastic Container Service**, then pick the
   **Elastic Container Service Task** use case below it. → **Next**.
   > It must be *Elastic Container Service Task* (trusts
   > `ecs-tasks.amazonaws.com`), **not** *Elastic Container Service*. Picking
   > the wrong one produces a role that tasks cannot assume.
4. **Permissions:** search `AmazonECSTaskExecutionRolePolicy`, tick it. → **Next**.
5. **Role name:** `ecsTaskExecutionRole` (exact spelling and case).
6. **Create role**.

### 2b. `ecsInfrastructureRoleForExpressServices`

This one needs a trust policy the wizard doesn't offer as a preset.

1. **IAM** → **Roles** → **Create role**.
2. **Trusted entity type:** *Custom trust policy*. Replace the JSON box with:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "AllowAccessInfrastructureForECSExpressServices",
         "Effect": "Allow",
         "Principal": { "Service": "ecs.amazonaws.com" },
         "Action": "sts:AssumeRole"
       }
     ]
   }
   ```
   → **Next**.
3. **Permissions:** search `AmazonECSInfrastructureRoleforExpressGatewayServices`,
   tick it. → **Next**.
4. **Role name:** `ecsInfrastructureRoleForExpressServices` (exact).
5. **Create role**.

> IAM is eventually consistent. If the first deploy fails with *"Unable to
> assume the service linked role"*, wait a minute and re-run it.

---

## Step 3 - Store the two secrets

`SUPABASE_SERVICE_ROLE_KEY` bypasses RLS and `DATABASE_URL` embeds the Postgres
password. Neither belongs in plain env config or in GitHub.

Do this **twice** - once per secret:

1. Console → **Secrets Manager** → **Store a new secret**.
2. **Secret type:** *Other type of secret*.
3. Select the **Plaintext** tab and replace its contents with the raw value -
   just the key/URI itself, no quotes, no braces, no trailing newline.
   > Stay on **Plaintext**. If you use *Key/value*, the secret becomes a JSON
   > object and the container receives `{"key":"..."}` instead of the value.
4. **Encryption key:** leave `aws/secretsmanager`. → **Next**.
5. **Secret name:**
   - `emma/test/supabase-service-role-key`
   - `emma/test/database-url`
   → **Next** → **Next** → **Store**.

Then collect both ARNs: click each secret → copy **Secret ARN** (ends in a
6-character random suffix, e.g. `...:secret:emma/test/database-url-AbCdEf`).
Keep them for Step 5.

### 3a. Let the execution role read them ← don't skip this

`AmazonECSTaskExecutionRolePolicy` does **not** grant Secrets Manager access.
This is the single most common cause of tasks that start and immediately die.

1. **IAM** → **Roles** → `ecsTaskExecutionRole`.
2. **Add permissions** → **Create inline policy**.
3. Switch to the **JSON** tab, replace the contents (substitute your account ID):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "secretsmanager:GetSecretValue",
         "Resource": "arn:aws:secretsmanager:ap-southeast-1:<ACCOUNT_ID>:secret:emma/*"
       }
     ]
   }
   ```
4. **Next** → **Policy name:** `EmmaReadSecrets` → **Create policy**.

---

## Step 4 - Let GitHub into AWS (OIDC, no access keys)

GitHub mints a short-lived token and assumes an AWS role. No long-lived AWS
credentials are ever stored in GitHub.

### 4a. Register GitHub as an identity provider

1. **IAM** → **Identity providers** → **Add provider**.
2. **Provider type:** *OpenID Connect*.
3. **Provider URL:** `https://token.actions.githubusercontent.com`
   → click **Get thumbprint**.
4. **Audience:** `sts.amazonaws.com`
5. **Add provider**.

> If it says the provider already exists, it's registered - move on.

### 4b. Create the deploy role

1. **IAM** → **Roles** → **Create role**.
2. **Trusted entity type:** *Web identity*.
3. **Identity provider:** `token.actions.githubusercontent.com`.
   **Audience:** `sts.amazonaws.com`.
4. Fill in the GitHub scoping fields that appear:
   - **GitHub organization:** `cherry-hei`
   - **GitHub repository:** `emma-ai-mvp-frontend-MVP-`
   - **GitHub branch:** `develop`
   → **Next**.
5. **Permissions:** search `AmazonEC2ContainerRegistryPowerUser`, tick it.
   → **Next**.
6. **Role name:** `github-actions-emma-api` → **Create role**.

### 4c. Add the Express Mode deploy permissions

1. Open the new `github-actions-emma-api` role.
2. **Add permissions** → **Create inline policy** → **JSON** tab:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ecs:CreateCluster",
           "ecs:RegisterTaskDefinition",
           "ecs:CreateExpressGatewayService",
           "ecs:UpdateExpressGatewayService",
           "ecs:DescribeExpressGatewayService",
           "ecs:DescribeClusters",
           "ecs:DescribeServices",
           "ecs:ListServiceDeployments",
           "ecs:DescribeServiceDeployments",
           "ecs:TagResource",
           "ecs:UntagResource",
           "iam:PassRole"
         ],
         "Resource": "*"
       }
     ]
   }
   ```
3. **Next** → **Policy name:** `DeployExpressService` → **Create policy**.
4. Confirm the **Trust relationships** tab shows a `token.actions.githubusercontent.com:sub`
   condition of `repo:cherry-hei/emma-ai-mvp-frontend-MVP-:ref:refs/heads/develop`.
   This is what restricts the role to this repo and branch.

AWS side done. ✅

---

## Step 5 - Configure the GitHub repo

The workflow at [`.github/workflows/deploy-api.yml`](.github/workflows/deploy-api.yml)
reads everything from **repository variables** - nothing is hardcoded, and no
secret *values* enter GitHub (only Secrets Manager ARNs, which are just
identifiers).

GitHub → your repo → **Settings** → **Secrets and variables** → **Actions** →
the **Variables** tab → **New repository variable**, once per row:

| Variable | Value |
|---|---|
| `AWS_REGION` | `ap-southeast-1` |
| `AWS_ACCOUNT_ID` | your 12-digit account ID |
| `ECR_REPOSITORY` | `emma-ai-api` |
| `ECS_SERVICE` | `emma-ai-api` |
| `ECS_CLUSTER` | `default` |
| `APP_ENV` | `test` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | anon / public key |
| `CORS_ORIGINS` | `http://localhost:3001` for now - real UI origin comes in Step 7 |
| `SECRET_ARN_SERVICE_ROLE_KEY` | service-role-key ARN from Step 3 |
| `SECRET_ARN_DATABASE_URL` | database-url ARN from Step 3 |

> Use the **Variables** tab, not *Secrets*. The workflow reads `vars.*`; values
> put under *Secrets* would arrive empty. Nothing here is confidential -
> `SUPABASE_ANON_KEY` is designed to be public and ARNs are just identifiers.

---

## Step 6 - First deploy

Commit the workflow and push:

```bash
git add .github/workflows/deploy-api.yml && git commit -m "ci: auto-deploy API to ECS Express Mode" && git push origin develop
```

Then GitHub → **Actions** → **Deploy API to AWS** → **Run workflow** (the
`workflow_dispatch` button) if the push didn't trigger it.

First run takes **~8–12 min** - it installs OR-Tools and pandas, then waits for
Fargate and the load balancer to come up. Later runs are much faster thanks to
the layer cache. The action **creates** the Express Mode service on this first
run; subsequent runs update it.

When it's green, the run's **Summary** page shows the endpoint, plus direct
links to `/health` and `/docs`. Open them:

- `<url>/health` → `{"status":"ok","service":"emma-ai-api"}`
- `<url>/docs` → interactive Swagger UI

You can also watch it in the console: **ECS** → **Express mode** (or
**Clusters → default**) → `emma-ai-api`. The **Resources** tab shows the ALB,
target group and scaling policy being provisioned; **Logs** shows container
output. If `/health` doesn't answer, go to **Troubleshooting** below.

---

## Step 7 - Point the UI at it

1. Deploy the UI per [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md), using this API URL as
   `NEXT_PUBLIC_API_URL`.
2. Come back and set the `CORS_ORIGINS` **repository variable** to the Amplify
   origin (comma-separated for several), e.g.
   `https://main.d1a2b3c4e5.amplifyapp.com`.
3. **Actions → Deploy API to AWS → Run workflow** to apply it.

From here on: **push to `develop` → the API redeploys.** ✅

---

## Changing configuration later

All runtime config lives in the GitHub **repository variables**, because every
deploy registers a fresh ECS task definition. So:

- **To change an env var:** edit the repository variable, then re-run the
  workflow. Editing it in the ECS console works only until the next deploy
  overwrites it.
- **To rotate a secret:** store the new value in Secrets Manager (the ARN
  doesn't change) and re-run the workflow so tasks restart and re-read it.
- **Never delete an entry** from the workflow's `environment-variables` or
  `secrets` list to "keep the old value" - anything absent is dropped from the
  new task definition.

---

## Troubleshooting

Container logs are the fastest diagnosis: **ECS → Clusters → default →
`emma-ai-api` → Logs**.

| Symptom | Cause / fix |
|---|---|
| Tasks start then stop; `ResourceInitializationError` fetching secrets | Step 3a missing, or its ARN pattern doesn't match your secret names. |
| Log: `FileNotFoundError: APP_ENV=test but neither .env.test nor a SUPABASE_URL environment variable is set` | `SUPABASE_URL` didn't reach the container - check the variable name in Step 5. |
| Container starts but secrets look like `{"key":"..."}` | The secret was stored as *Key/value* instead of **Plaintext** (Step 3). Re-store it. |
| Health check failing / target unhealthy | Container port must be `8080`, health path `/health`. Check the log for a startup traceback. |
| `500` + `db_error` on every call | `DATABASE_URL` / `SUPABASE_*` wrong, or the schema was never pushed - see [`SETUP_SUPABASE_DB.md`](SETUP_SUPABASE_DB.md). |
| **CORS error** in the browser | UI origin isn't in `CORS_ORIGINS`. Add it, re-run the workflow. Must match scheme + host exactly, no trailing slash. |
| `401 unauthorized` from clients | Expected without a bearer token - log in via `/auth/login` first. Not a deploy issue. |
| Actions: `Not authorized to perform sts:AssumeRoleWithWebIdentity` | The org/repo/branch in the Step 4b trust policy doesn't match what you pushed. |
| Actions: `repository does not exist` on push to ECR | ECR repo name or **region** mismatch - Step 1 vs the `AWS_REGION` / `ECR_REPOSITORY` variables. |
| Actions: `Unable to assume the service linked role` | IAM eventual consistency. Wait a minute, re-run. |
| Env var silently disappeared after a deploy | See *Changing configuration later* - the workflow must carry the complete set. |

**Cost (rough):** 1 vCPU / 2 GB Fargate always-on ≈ **$25–35/month**, plus the
Application Load Balancer at ≈ **$18–20/month**, plus cents for ECR storage.
Express Mode itself adds no charge. Budget **~$45–60/month** per always-on
environment; the ALB is a fixed floor, so avoid running `test` and `production`
in parallel longer than you need to.

**Deliberate pilot setting:** the workflow pins min = max = **1 task**. Job state
(`optimization_jobs`) lives in Postgres so polling works across instances, but an
`/optimize-roster` background solve runs in the process that received it - one
task avoids that entirely. Raise `max-task-count` once solves move off the
request process.

**Deploying a different branch:** change `branches:` in the workflow **and** the
branch condition in the Step 4b trust policy. Both must agree.

---

## Appendix - CLI equivalents

Same setup, for reference or scripting. Assumes
`AWS_REGION=ap-southeast-1` and `AWS_ACCOUNT_ID` are exported.

| Console step | CLI |
|---|---|
| 1 · ECR repo | `aws ecr create-repository --repository-name emma-ai-api --region "$AWS_REGION"` |
| 2a · execution role | `aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'` then `aws iam attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy` |
| 2b · infrastructure role | `aws iam create-role --role-name ecsInfrastructureRoleForExpressServices --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs.amazonaws.com"},"Action":"sts:AssumeRole"}]}'` then `aws iam attach-role-policy --role-name ecsInfrastructureRoleForExpressServices --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices` |
| 3 · secrets | `aws secretsmanager create-secret --name emma/test/database-url --secret-string "<uri>" --region "$AWS_REGION" --query ARN --output text` |
| 3a · read policy | `aws iam put-role-policy --role-name ecsTaskExecutionRole --policy-name EmmaReadSecrets --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:emma/*\"}]}"` |
| 4a · OIDC provider | `aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com` |
| 6 · inspect service | `aws ecs describe-express-gateway-service --service-arn "arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT_ID:service/default/emma-ai-api" --region "$AWS_REGION"` |
| - · tail logs | `aws logs tail /ecs/default/emma-ai-api --follow --region "$AWS_REGION"` |

---

## What's next

API is live. Point the UI at its URL → [`SETUP_UI_AWS.md`](SETUP_UI_AWS.md).
