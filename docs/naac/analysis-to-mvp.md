# Reviewed analysis → Generate → linked export

This adapter implements D-040 in the existing roster workspace. It does not
publish a roster or activate a facility's observed patterns without review.

## Operator path

1. Analyse the authorised source files and complete the entire shift dictionary,
   including lifecycle, exact minute credit, split/night duty windows, task codes,
   PH/AL fractions and original source references. Keep employee records local.
2. Produce a proposed configuration matching `roster-analysis.schema.json`.
   `roster-analysis.synthetic.json` is an invented format example, not NAAC rules.
   Keep confirmed rules and historical demand estimates distinguished in sources.
3. Reconcile the profile with the organisation's existing shift definitions and
   staff ranks. Generation checks exact code credit and does not create or alter
   that dictionary. Every active employee needs a role mapping. A weekly contract
   reference is separate from an explicitly agreed maximum weekly limit.
4. As OWNER, open **Roster → Analysis settings**, import the file, inspect it,
   explicitly confirm the review, and save. This creates a version of the existing
   `facility_json_configs` key `roster_analysis`; no new database column is needed.
5. Create/select a **42-day period beginning Monday**, then select its source
   version and the saved analysis under **Generate from**. Monthly views still
   use the same six-week period. Click **Generate roster options**.
6. CP-SAT expands reviewed weekday/PH demand and honours source nonworking cells
   plus approved leave with explicit role/leave-code mappings. Unfilled staff
   dates receive the reviewed off code. It does not invent approved AL or PH.
7. Select the resulting A/B/C version and click **Export roster**. The authenticated
   request names both period and version. The export reads the saved analysis
   snapshot, not a subsequently edited configuration. An incomplete writeback is
   archived, cannot be exported/published, and does not replace prior drafts.

## Linked workbook contract

One scoped roster supplies 17 sheets: `更期代號註解`, `代號及時數(old)`,
`代號及時數`, `覆診地點代號`, six weekly sheets, `Hours`, `PH & Off`,
`DO更次數`, `AP更`, `C更男女`, `N更男女`, `用膳代號`.

The weekly code cell contains only the shift code; tasks have separate cells.
Formula lookups drive hours, PH/AL fractions, duty-officer and A/P/C/N counts.
An explicitly configured `duty_officer_task_code` also counts exact tokens in
the weekly task cells (for example `#`); it does not impose next-day rest.
O, NO and O+NO are distinct. They are literal NAAC code meanings in this adapter,
not universal definitions of statutory rest days. Gender is supplied data, never
guessed from names. Missing codes/assignments and unknown carry do not settle as
zero. `Hours` includes six weekly comparisons; `PH & Off` includes month slices
with covered days, AL, PH, O, NO, credit hours and working days. Month slices are
allocations, not monthly hours targets or verified entitlements.

Opening PH, opening hour difference and closing PH/NO inputs remain blank.
Period PH reference deduction comes from the reviewed calendar; weekly comparison
uses actually allocated PH. Those comparisons reconcile only once PH allocation
and carry are reviewed. Excel must recalculate on opening; the writer does not
provide formula caches. Editing Excel does not update the application or re-run
coverage, qualification or rest validation.

The generated layout is functional and does not require a private customer template
on the server. Reference sheets explicitly disclose absent historical dictionaries,
escort-place references and meal allocation. Their presence does not mean those
data or task allocations have been reconstructed. It is not a pixel-identical
copy of a customer's historical workbook. The older approved-template adapter
remains available for versions without an analysis snapshot, with the same
17-sheet manifest and separate task columns.

## Runtime limits and release evidence

Current analysis drafts deliberately fail the publication gate: complete task
allocation, carry settlement and PH pairing are not yet recorded by this adapter.
The existing generic rules still run; their historical defaults must be reviewed
for the intended facility. This change does not certify legal ratios, approve
leave/OT, settle financial-year agency budgets, or call a language model.

The profile freezes its config ID/version/digest into existing option-score JSON.
Live staff, leave, contracts, ratio rules and tasks are still validated by the
existing services; this is not a transactionally frozen copy of every database
input. Changing them requires fresh generation and validation.

Local verification uses invented data and the in-memory database adapter. It is
separate from deployed database RLS/trigger acceptance and real-facility UAT.
No migration or deployment is included. Kien review and Founder approval for the
exact reviewed SHA remain required before merge/release.
