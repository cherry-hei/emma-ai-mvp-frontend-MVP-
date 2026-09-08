# Roster Rule-Check UX Reference

**Date:** 2026-09-08  
**Purpose:** Inform a minimal Emma Roster UX refinement without changing deterministic rule authority or unrelated screens.

## International patterns

| Product／source | Observed pattern | Emma implication |
|---|---|---|
| Oracle Workforce Scheduling | Validates schedule changes against rules, work patterns, hours and absences; shows warnings in the edit drawer; supports whole-schedule validation; shows the most recent validation summary again before publish. | Keep validation inside Roster. Show a compact summary above the grid, details in a drawer, and re-confirm the latest result at publish. |
| RosterElf | Marks affected shifts with small warning icons; header counter filters the affected shifts; warnings guide managers but do not automatically block every action. | Keep the calendar large. Add cell-level markers where issue location is known and let summary counters filter／focus affected cells. |
| Sprinklr Schedule Scenarios | Uses a third-pane Alerts panel; groups by alert type; distinguishes Hard Alerts that block publish from Soft Alerts that do not; clicking an alert navigates to the affected agent／section. | Use a right-side Rule Review drawer with Blocking, Warning and Advisory groups. Each item should identify the affected staff／date and offer one next action. |
| Humanity Schedule | Detects policy／qualification conflicts during schedule construction and keeps edit history for audit readiness. | Run deterministic checks after relevant edits and retain rule evidence／audit; AI may explain but must not alter verdicts. |

## Recommended Emma pattern

The roster grid remains the primary workspace. A single compact status bar should show **Ready to publish**, **Needs attention**, or **Checking**, followed by counts for Blocking, Warning and Advisory. It should avoid a generic red “system error” appearance. A **Review rules** button opens a side drawer without reducing grid height.

The drawer groups issues by severity and rule category, gives each issue plain-language impact, staff／date context when available, deterministic evidence and one operational next step. Blocking issues prevent publish. Warnings require manager review but do not automatically prevent publish unless the configured rule is hard. Advisory items are informational.

Emma AI should be offered only as an optional **Explain this result** action for the selected deterministic issue or current validation summary. It opens the existing Emma AI Compliance Q&A workspace with roster／date／rule context. The AI cannot change severity, eligibility, pass／fail or publish status.

The official Oracle page was also visually checked and confirms that the most recent validation result is surfaced again in the publish flow instead of occupying the schedule canvas permanently. The official Sprinklr page was visually checked and confirms a separate alerts pane with explicit Hard and Soft severity, where hard time-off conflicts block publishing and provide a direct revise action. These patterns support a compact roster status strip plus an on-demand review drawer rather than a tall inline error list.

## Sources

[1]: https://docs.oracle.com/en/cloud/saas/readiness/hcm/24b/wosc-24b/24B-workforce-scheduling-wn-f32299.htm "Oracle — Validate Workforce Schedule Introduction"
[2]: https://www.rosterelf.com/support/knowledge-base/scheduling-and-rostering/roster-warnings "RosterElf — Understand roster warnings"
[3]: https://www.sprinklr.com/help/articles/schedule-scenarios/alerts-in-schedule-scenarios/686539f620753412ba1b101b "Sprinklr — Alerts in Schedule Scenarios"
[4]: https://tcpsoftware.com/products/humanity/compliance/ "Humanity Schedule — Compliance and conflict management"
