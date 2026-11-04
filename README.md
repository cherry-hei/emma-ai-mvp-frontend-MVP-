# Emma AI

Roster planning for Hong Kong care homes. Next.js serves the manager and staff
interfaces. FastAPI owns the workflows, exports and deterministic checks.
PostgreSQL, authentication and row security use the existing Supabase server.

## Run

Frontend, from the repository root:

```powershell
npm ci
npm run dev:next
```

Backend, from `emma-ai-app`:

```powershell
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

Set `NEXT_PUBLIC_API_URL` in the root `.env.local`. Configure the existing server
in `emma-ai-app/.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` and `DATABASE_URL`. Templates list names only; never
commit credentials. There is no need to create a local database.

Frontend: `http://localhost:3001`. API: `http://localhost:8000`.
Swagger: `/docs`. OpenAPI: `/openapi.json`.

## Layout

```text
src/                        Next.js pages, components and API client
emma-ai-app/api/             FastAPI routers and permission checks
emma-ai-app/emma_core/       Models, services, importers and solver
emma-ai-app/supabase/        Database migrations
emma-ai-app/scripts/         Provisioning and deployment checks
emma-ai-app/tests/           Service, API and server tests
```

Keep workflows in services and routers thin. Reuse the existing rule engine;
neither the UI nor a language model should decide compliance. Resolve records
through the caller's facility before using a service client for trusted writes.

## Current work

- Approved leave updates the manual and published roster in one database
  transaction. The original duty, tasks, completion state and task exceptions
  remain available for revocation. Overlapping approvals are rejected.
- Events accept named participants and custom types. Validation checks that
  designated staff cover the full event window.
- Compliance Q&A supports staffing ratios, breach minutes, certificate
  thresholds and roster validation. Missing or ambiguous input needs clarification.
- Bedrock supports configured Grok and Kimi profiles. The backend
  remains responsible for verdicts, eligibility and replacement ranking.
- NAAC workbook export uses an approved 18-sheet template and cell mapping.
  The engine is implemented; source-workbook comparison still needs the actual
  workbook. The rules PDFs, RBAC document and addendum are not that template.
- Report previews ignore responses from an old period or signed-in identity.
  Downloads refresh expired sessions, retain draft filenames and reject empty
  or unexpected file responses. Changing the period cancels an active download.

The source changes are not deployed until the normal deployment workflow runs.
Passing synthetic tests does not certify live model access or client UAT.

## NAAC data and exports

The shipped dictionaries are under `emma-ai-app/emma_core/importers/data`.
The duty CSV has 279 rows, including a repeated B12 and the `/` spacer; the
loader yields 277 duty codes. Escort rows yield 18 location codes. Paid AL/SL
hours do not mean that a person is on duty.

Workbooks and employee-specific preferences stay outside git. Personal rules
belong in facility configuration. Do not commit real names, staff lists,
rosters, certificates or leave attachments.

Provisioning uses an existing server and synthetic config:

```powershell
cd emma-ai-app
python scripts/provision_tenant.py scripts/tenants/naac.json --dry-run
python scripts/provision_tenant.py scripts/tenants/naac.json
```

For the full workbook, configure `NAAC_WORKBOOK_TEMPLATE` and
`NAAC_WORKBOOK_MAPPING`. Each accepts a local path or private `s3://` object.
The deployment role needs read access to those objects. Inspect the approved
workbook before writing its mapping:

```powershell
python scripts/inspect_naac_template.py path/to/approved.xlsx --output path/to/mapping.json
```

Complete the six weekly sheet mappings, staff rows, date and duty columns,
summary columns, preserved label ranges and metadata cells. The mapping is tied
to the template SHA-256. An incorrect sheet count, unknown duty mapping or
insufficient row capacity fails the export instead of dropping data.

`GET /exports/naac/tahduty.xlsx?period_id=...` downloads the workbook for the
caller's facility. An optional `version_id` must belong to that same period and
facility. Existing single-sheet downloads remain under `/reports/download/`.

## AI

Set `BEDROCK_ENABLED=true`, `BEDROCK_REGION` and `BEDROCK_MODEL_ID` to enable
Bedrock. Use the AWS task role, not credentials stored in the frontend.
`BEDROCK_TIMEOUT_SECONDS` defaults to 30. The deployment workflow accepts
`BEDROCK_TASK_ROLE_ARN`; an example policy lives in
`emma-ai-app/scripts/bedrock_task_policy.example.json`.
Fill in its account and source region placeholders. The policy covers the Grok
or Kimi profile, foundation model and default project, plus profile inspection. Grant
the testing identity access separately from the deployed ECS task role.
Set `AI_SYNTHETIC_FACILITY_IDS` to the comma-separated IDs of tenants whose data
has been confirmed synthetic. An empty list disables external models for every
tenant, even when Bedrock is enabled. Real-data tenants must stay off this list.
The deployment workflow checks this setting before running migrations.

Set `BEDROCK_MODEL_ID=global.moonshotai.kimi-k3` for Kimi K3. The policy's
`MODEL_ID` is `moonshotai.kimi-k3`; its `INFERENCE_PROFILE_ID` is
`global.moonshotai.kimi-k3`. Grok uses `xai.grok-4.7` and `global.xai.grok-4.7`.
Kimi uses InvokeModel with reasoning disabled for these short explanations.
It does not accept the temperature parameter used by the Grok Converse route.

A Hong Kong application can call an overseas Bedrock endpoint. The application's
hosting region does not establish where inference runs. Verify the actual profile
and account rather than assuming `ap-east-1` supports the request:

```powershell
python scripts/verify_bedrock.py --region SUPPORTED_REGION
python scripts/verify_bedrock.py --region SUPPORTED_REGION --invoke
```

For local SSO testing, sign in with `aws sso login --profile PROFILE_NAME` and
add `--profile PROFILE_NAME` to either command. Local model tests do not need a
deployment. If profile inspection is denied, `--invoke` still attempts the model
call and reports that the routing configuration could not be verified.

The second command makes a small synthetic model call. Unknown questions stay
local. Outgoing evidence excludes free text, replaces identifiers with request
aliases and passes through the privacy gate. A timeout or rejected explanation
returns the deterministic answer. `GET /ai/status` shows configuration; it does
not prove that AWS has accepted a live invocation.

Singapore access with a global Kimi profile does not guarantee Hong Kong-only
processing. The existing API is in Singapore and the configured database is in
Seoul. The 31 October scope permits an authorised internal trial outside Hong
Kong after target, access and backup review. External model access remains
limited to the approved synthetic tenants. Aliased staff records can still be
personal data; removing names does not by itself approve external AI processing.

`POST /ai/compliance-qa` accepts `question`, `date`, `roster_version_id`,
`unit_id`, `intent` and `explain`. Setting `explain=false` uses rules only.
The caller needs compliance read access. Answers include evidence, source rule
references and available model request, latency and token metrics. Q&A audit
records do not store raw questions or prompts.
Chinese questions request Traditional Chinese explanations; other questions
request English. The original question stays local in both cases.

## Verify

From `emma-ai-app`:

```powershell
python -m pytest tests/test_ai_acceptance.py tests/test_bedrock_gateway.py tests/test_naac_export.py tests/test_mvp_launch_api.py -q
$env:EMMA_RUN_SERVER_TESTS = '1'
python -m pytest tests/test_m2_server.py -q
python scripts/run_ai_acceptance.py --output ../docs/ai_acceptance.json
```

Server tests use the configured server and roll back their migrations and
invented rows. They do not create another database. Run them when the server is
available; the flag keeps them out of ordinary test runs.

The 13 AI cases verify backend behaviour with synthetic providers. Their report
leaves live model verification and human scoring unset. Test the selected model
and client UI separately before acceptance.

From the repository root:

```powershell
npx tsc --noEmit --incremental false
npm run test:ui
npm run build
```

## Deployment and domain

The API workflow applies migrations and deploys the backend on pushes to `main`.
Its migration command uses `--yes` because CI cannot answer hosted-change prompts;
review and release approval must happen before pushing or invoking the workflow.
Amplify builds the frontend separately. Set its `NEXT_PUBLIC_API_URL` to the
intended API. Add the final manager and Staff App origins to `CORS_ORIGINS`.
Release approval must identify the exact source SHA and target. Review migrations
24 and 25 against a verified backup before running the workflow. Reverting an
ECS image does not undo leave decisions or database changes. If a release fails,
disable external models and restore the previous image; review database recovery
separately rather than automatically reversing accepted staff decisions.
The migration preflight runs with read-only transactions and reports aggregate
counts. Missing schema is skipped only for unapplied migrations; permission,
timeout and drift errors block the release. It does not verify backup freshness.
When Bedrock is enabled, CI verifies the task role before migrations; its deployer
needs `iam:GetRole` and `iam:PassRole` on that exact role.

Prepare scoped policies, workflow variables, migration hashes and rollback notes
without changing AWS resources:

```powershell
python emma-ai-app/scripts/prepare_bedrock_release.py --service-arn SERVICE_ARN --runtime-role ROLE_NAME --output docs/release-plan.json
```

Add `--inspect-aws --profile PROFILE_NAME` for current account, service, role and
inference-profile checks. Add `--synthetic-facility-id UUID` only for an approved
synthetic tenant. The plan stays gated until the source commit, backup, runtime
permissions and release have been reviewed; it never provisions or deploys.

```powershell
python scripts/launch_readiness.py --api https://API --manager https://MANAGER --staff https://STAFF
python scripts/configure_domain.py --app-id APP_ID --domain example.org --region AWS_REGION
```

Domain setup previews by default. `--apply` creates the Amplify association;
adding `--godaddy` writes its CNAME records using `GODADDY_API_KEY` and
`GODADDY_API_SECRET` from the environment. Apex-domain routing needs a separate
DNS plan. Check certificate validation and HTTPS after DNS propagation.

Keep account access, deployment approval and client UAT separate from code
completion. Real-data use must follow the agreed hosting arrangement.
