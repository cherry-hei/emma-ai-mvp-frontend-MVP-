# MVP cross-check — quote spreadsheet vs ClickUp board

Sources: the 7-week quote sheet (`Emma AI — MVP (7-week) & Phase 5-8 Quote`, gid
1431884318) and the ClickUp workspace *Emma AI* (90161616551), read 2026-07-31,
**re-counted 2026-08-01** after Cherry's config files landed.

## What changed on 1 Aug

Cherry attached the NAAC files to ClickUp 2.2 and 4.1 on 31 Jul, as links inside
the comment bodies rather than as task attachments — which is why the earlier API
check for attachments came back empty and the files read as still missing.

**All three hard blocks are cleared.** 2.2, 2.3 and 4.1 are built against the real
data; see `docs/naac/README.md` for what was extracted and what was deliberately
not committed. SA.7 was also built out, which closes the Staff App backend.

Two things need Cherry's attention and are flagged on the tasks:

1. **The files are not personal-data-free.** Her covering comment says they are;
   her own workbook guide says the roster sheets contain staff names, and the
   rules document names five people with individual quotas and preferences. The
   second reading is right. Code dictionaries were committed, the two 500 KB
   workbooks were not, and the five names are replaced with `STAFF_Q1`…`STAFF_N1`.
2. ~~3.3 still has the CSV-vs-PDF scope conflict~~ — **decided 1 Aug: build it.**
   Rather than let the demo fail on a disagreement about scope, the rendering
   layer is now in (`services/render.py`). CSV, XLSX and PDF from the same
   generator output, so the manager's spreadsheet and the PDF sent to SWD can
   never disagree about what the roster said. This goes beyond the signed
   data-only scope and should be reflected commercially.

## Headline: the board and the quote disagree about what "MVP" means

The ClickUp board holds **47 tasks in one flat list** with no MVP / post-MVP
divider. The quote splits the same work into two separately capped, separately
gated contracts. Cross-referencing them, the boundary lands exactly on a task
count the quote already states:

| | Quote says | Tasks | Board tasks |
|---|---|---|---|
| **MVP** (7 weeks, cap USD 6,695) | Phase 0–4 + Phase 7 reports (data only) + Staff App PWA backend | **27** | `0.1–0.2`, `1.1–1.6`, `2.1–2.3`, `3.1–3.4`, `4.1–4.3`, `7.1–7.2`, `SA.1–SA.7` |
| **Phase 5–8** (post-MVP, cap USD 5,668) | Compliance engine auto-judge, AI, Emergency Cover, OT, QA, native app | **15+** | `5.1–5.5`, `6.1–6.2`, `8.1–8.2`, `EC.0–EC.8`, `QA i18n` |

The MVP column sums to **exactly 27**, matching the quote's own task count. That
is strong evidence the mapping is right.

The quote's own sorting rule, verbatim: *"anything WITHOUT AI belongs in MVP;
anything requiring AI or compliance auto-judge is Phase 5-8."*

### Consequence 1 — 19 board tasks are not MVP work

`5.x`, `6.x`, `8.x` and every `EC.*` are Phase 5–8. Asking for "all MVP tasks
complete" does **not** include them. Real MVP remaining is 20 tasks, not 39.

### Consequence 2 — Phase 5–8 is contractually gated, and we are already past the gate

> **Phase 5-8 Start:** Only after all MVP milestones accepted AND Emma AI written
> approval. Cap 436h / USD 5,668.

The repository already contains Phase 5: migrations
`20260729000010_phase5_compliance_engine.sql` through `…13`, plus
`test_phase5_*.py` (roughly 3,000 lines of tests). That work was built **before**
MVP acceptance and before the written approval the quote requires.

**This needs raising with Cherry, not buried.** Either it counts against the
Phase 5–8 cap and should be invoiced accordingly, or it was delivered outside the
contract. It is not a technical problem — the code is tested and passing — but it
is a commercial one, and it is better raised by us than discovered by them.

### Consequence 3 — the frontend is not in our scope at all

> **Basis / Notes 1:** *"Costing = Backend (BE) + Test only. Frontend (HTML + PWA)
> done by Emma AI."*

This reframes the entire UI complaint. The roster page, the Staff Portfolio cards,
the modals — all Emma AI's deliverable, not ours. What actually happened is that
our API-integration work **edited Cherry's frontend**, dropping 12 of her files
(both modals, the whole `roster/` component set, `lib/data.ts`, 5 export routes)
and replacing the roster with `RealRosterBoard.tsx`.

So "the UI is not the same as my design" is not a missed requirement on our side —
it is us having modified a deliverable that was not ours to modify. The correct
posture going forward: **restore her components, wire them to the API, and never
redesign.** Any UI change should be a request to her, not a commit by us.

## Per-task status against the MVP 27

Legend: ✅ done · 🟡 partial · ⬜ not started · 🚫 blocked

### Phase 0 — Decision & Scope Lock (Week 1, 1%) — **complete**
| Task | Status | Evidence |
|---|---|---|
| 0.1 Lock MVP backend architecture | ✅ | `ARCHITECTURE_DECISIONS.md`, `architecture_decisions` register |
| 0.2 Lock MVP scope, defer Phase 2+ | ✅ | `MVP_SCOPE.md`, `project_scope` register |

### Phase 1 — Foundation, Security & Data Import (Week 1–2, 20%) — **6 of 6**
| Task | Status | Evidence |
|---|---|---|
| 1.1 Role-based login and permissions | ✅ | `permissions.py` + guards + menu filtering, plus the recommendation record — `request_recommendations` (migration 16), the recommend endpoint, and the approval queue returning recommendations attached. 17 tests in `test_mvp_recommendations.py`. **Backend closed**; the approver *screen* still needs Cherry's answers to questions 5.1 and 5.2 |
| 1.2 Facility-level data isolation | ✅ | `20260721000002_rls_tenancy.sql`, `test_rls_isolation.py` |
| 1.3 Audit log with before/after | ✅ | `services/audit.py`, `trg_protect_audit_log` |
| 1.4 Import real roster Excel | ✅ | `importers/`, `services/imports.py`, `test_mvp_import.py` |
| 1.5 Calendar / PH / special-pay schema | ✅ | `services/calendar_days.py`, migration 14 |
| 1.6 Compliance/security evidence checklist | ✅ | `SECURITY_EVIDENCE.md` (role matrix corrected 2026-07-31), `evidence_items`. 4 of 11 controls still pending external evidence — stated in the doc |

### Phase 2 — Core Data Model (Week 2–3, 9%) — **2 of 3 done, 1 partial**
| Task | Status | Evidence |
|---|---|---|
| 2.1 Staff profile and contract model | 🟡 | Backend model exists. **"Add staff" button has no handler**; profile cards do not match the demo. Frontend half — Cherry's deliverable per the quote's basis notes |
| 2.2 Facility-specific JSON/rule config | ✅ | Framework plus the real NAAC profile: dual 44h/49h week per role, rest-day cycles, `#` quota shape, meal windows, coverage minimums (`facility_config.NAAC_CONFIGS`, `services/naac_seed.py`, `scripts/seed_naac_config.py`) |
| 2.3 Shift definition dictionary | ✅ | **277 duty codes** loaded from the home's own `代號及時數` sheet, plus the code grammar implemented independently as a cross-check (`importers/naac.py`). 174 codes agree; the 5 that do not are named and explained in `test_mvp_naac.py`. Sequencing rules — AN→NO→O, no P before AN, no A7 after A230/E, no consecutive kitchen, 8-day run cap — in `evaluate_sequence_rules` |

### Phase 3 — Roster Operations (Week 3–4, 17%) — **0 of 4**
| Task | Status | Notes |
|---|---|---|
| 3.1 DB-backed roster calendar | ⬜ | Assigned to Cherry Siu |
| 3.2 Manual roster edit flow | 🟡 | Backend complete. Cherry's `CreateShiftModal.tsx` **restored**; not yet mounted or wired — her deliverable |
| 3.3 Roster save, publish and export | ✅ | All four parts: `POST /rosters/{id}/save-draft`, `POST /validate-roster`, `POST /rosters/{id}/publish` (gated on validation — a roster with hard violations cannot be published), and **`GET /reports/download/{type}.{csv\|xlsx\|pdf}`** (new 1 Aug). Export controls still need mounting on the page |
| 3.4 Limited roster option comparison | ⬜ | `AiOptionsModal.tsx` exists as a starting point |

### Phase 4 — Task-Based Scheduling (Week 4–5, 14%) — **2 of 3**
| Task | Status | Notes |
|---|---|---|
| 4.1 Task-code definitions and assignment | ✅ | 59 NAAC task markers seeded; 18 escort location codes. Cherry confirmed the location is **per assignment**, so it is a column on `task_assignments` plus `escort_locations` as the dictionary (migration 18, `services/escort.py`). Unknown codes are stored and flagged, never rejected |
| 4.2 Special event staffing overlays | 🟡 | Backend done. Cherry's `CreateEventModal.tsx` **restored**; not mounted or wired — her deliverable |
| 4.3 Floor/unit-level operational staffing | ✅ | Marked complete on the board |

### Phase 7 — Reporting (Week 5–6, 12%) — **2 of 2 on the backend**
No longer "data only" — the rendering layer built for 3.3 on 1 Aug serves these too.

| Task | Status | Notes |
|---|---|---|
| 7.1 Export basic compliance report | 🟡 | `POST /reports/compliance` plus CSV/XLSX/PDF download, role-guarded. Not yet accepted against the demo |
| 7.2 Export roster report | 🟡 | `POST /reports/roster` plus the same three formats. Cherry's 5 export route handlers were dropped from `main` and still need restoring on the page |

All eleven report types get all three formats for free — every generator returns
the same `{meta, columns, rows}` shape, so one XLSX renderer and one PDF renderer
cover the lot.

### Staff App PWA backend (Week 5–7, 22%) — **7 of 7 backend complete**
| Task | Status | Evidence |
|---|---|---|
| SA.1 Staff request API | ✅ | `test_mvp_staff_app.py`, fan-out to recommenders via the permission matrix |
| SA.2 Staff calendar API | ✅ | marked complete on the board |
| SA.3 Task tick + exception | ✅ | `services/tasks.py` — closed reason-code list, exception written before the status flips |
| SA.4 Notifications + manager SSE | ✅ | `routers/notifications.py`, `services/notifications.py` |
| SA.5 Manager approval + auto-lock | ✅ | `services/roster_locks.py`; approving is what locks the cell |
| SA.6 Shift swap | ✅ | `services/swaps.py` — three-party flow |
| SA.7 Certificate vault + expiry | ✅ | **new 1 Aug** — `services/certificates.py`, migration 19. Warning ladder at 90/60/30/14/7 days, then weekly once lapsed, each stage sent exactly once; renewal resets it |

This was **22% of the MVP payment** and the largest unstarted block on 31 Jul. The
backend is now done, 194 tests across `test_mvp_staff_app.py` and
`test_mvp_certificates.py`. The **PWA frontend is Emma AI's** per the quote's basis
notes — still unconfirmed, question 9 in `CHERRY_CONFIRMATIONS.md`.

### Delivery & Warranty (Week 7, 5%) — ⬜
Handover, source code, knowledge transfer. 30 days warranty starts at acceptance.

## MVP completion, honestly counted

As at 1 Aug, after the NAAC unblock and SA.7:

| | Count | Change since 31 Jul |
|---|---|---|
| ✅ Complete | 20 | +13 |
| 🟡 Partial — backend done, frontend outstanding | 6 | — |
| ⬜ Not started | 1 | −10 |
| 🚫 Blocked | 0 | −3 |
| **Total MVP** | **27** | |

**Every backend task in the MVP 27 is now built and tested.** What remains is
frontend wiring.

The six partials are all the same shape: the API is live and tested, and the
screen that calls it is Cherry's deliverable per the quote's basis notes
(*"Costing = Backend (BE) + Test only. Frontend (HTML + PWA) done by Emma AI"*).
They are 2.1 (Add staff), 3.2 (`CreateShiftModal` restored, not mounted), 3.4,
4.2 (`CreateEventModal` restored, not mounted), and 7.1 / 7.2 (endpoints and all
three formats live, not yet accepted against the demo). 3.1 is the one not
started, and it is assigned to Cherry.

## What blocks progress right now

1. ~~NAAC config files never arrived~~ — **cleared 1 Aug.** Attached to ClickUp
   2.2 and 4.1 as comment links; 2.2, 2.3 and 4.1 are built against them.
2. **Nothing is deployed yet — but the path is now built.** Status at end of
   1 Aug:

   | Step | State |
   |---|---|
   | Merge MVP work onto `main` | ✅ done locally, commit `25846ac`, **not pushed** |
   | CI migration step | ✅ added — read secret → pre-flight → migrate → build → deploy |
   | Migrations 18–20 rehearsed | ✅ on **dev**; ledger at 20, schema verified |
   | Migrations 10–20 rehearsed on a **production clone** | ❌ **not done** |
   | `secretsmanager:GetSecretValue` on the deploy role | ❌ not granted |
   | `git push origin main` | ⛔ blocked on the two rows above |

   Migrations run **before** the image on purpose: additive schema with old code
   survives the minute it lasts, new code on old schema is the 500s.

   `scripts/preflight_migrations.py` is read-only and checks the two things in
   10–20 that can only fail against a database with real history — **ten unique
   indexes** over existing data (`if not exists` prevents a second run, not a
   first-run collision, and a failure aborts the push half-way leaving the
   recorded schema version untrue) and **one DELETE** in migration 13 against
   `agency_assignments`. It fails the CI build rather than letting a partial
   push through.
3. **3.3 reporting format is unresolved.** The task says Excel/PDF; the signed
   scope says Phase 7 is data-only, JSON and CSV. Asked on 31 Jul, unanswered. If
   the demo expects a PDF, 3.3 / 7.1 / 7.2 fail acceptance on a disagreement
   rather than a defect.
4. **Personal data in the delivered files** — see the note at the top. Handled
   conservatively; Cherry needs to confirm the handling.
5. **Nine open questions** await Cherry — see `CHERRY_CONFIRMATIONS.md`. Numbers
   1 (files) and part of 5 are now answered.
