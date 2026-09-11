# Admin MVP Function Deduplication Map

**Status:** Approved direction from Cherry; implementation checklist  
**Design rule:** One task, one primary workspace. Cross-links may navigate to the owner workspace but must not recreate the same interaction.

## Verified NAAC workbook structure

The supplied NAAC source is a native `.xlsx` workbook, not an image-only file. It has 18 structured worksheets: shift-code dictionaries, six weekly roster sheets, and derived report sheets including Hours, PH & Off, DO count, A/P shifts, C-shift gender and N-shift gender. It also contains identifiable staff and operational data; it must not be uploaded to the current non-Hong-Kong production stack.

The workbook therefore defines the output contract for the Reports workspace: the report cards correspond to the NAAC workbook's derived sheets and are generated from the selected live roster version. The complete download is one six-week, multi-sheet NAAC workbook. A workbook upload is not a routine reporting task and must not appear in the everyday Reports workspace.

## Unique ownership

| Capability | Primary workspace | Remove from |
|---|---|---|
| Generate A/B/C roster options | Roster | No duplicate elsewhere |
| Manual roster editing and tasks | Roster | No duplicate elsewhere |
| Deterministic rule validation | Roster | Reports header and generic report KPI |
| Roster approval/publish | Roster | Reports and Compliance |
| Compliance Q&A | Emma AI (`/insights`) | Compliance tab |
| Emergency SL suggestion/explanation | Emma AI (`/insights`) | Alert operational modal |
| Send／withdraw／approve replacement offers | Alert Centre | Emma AI; Emma AI only links to Alert Centre |
| Staffing ratio／resident count／certification／audit dashboards | Compliance | No Q&A embedded here |
| NAAC-format current-roster reports and complete six-week workbook | Reports | No separate NAAC panel, routine workbook import or duplicate export block |
| Shift-code dictionary | Shift Codes | No Reports import |
| One-time NAAC code／historical migration | Controlled backend／migration process after HK gate | Reports and ordinary user navigation |

## Navigation decision

Emma AI remains the single top-toolbar shortcut. Remove the duplicate Emma AI item from the sidebar. Compliance remains in the sidebar because its dashboards are distinct from Q&A. Roster remains the full generate → edit → rule-check → publish workspace.

## Implementation edits

1. Remove `ComplianceQaPanel` from `/compliance`; default the page to Staffing Ratio.
2. Remove `NaacDataPanel` from Reports completely. The Reports page itself becomes the one NAAC export workspace, with report cards mapped to NAAC workbook sheets.
3. Rename Reports away from “Automated Report Engine”; remove Emma AI, active-violation and warning framing; add explicit period／roster-version context and one complete multi-sheet workbook download state.
4. Add an explicit generate → edit → rule-check → publish workflow strip to Roster and make button labels unambiguous.
5. Remove automatic AI suggestion invocation and AI explanation card from the Alert operational modal; keep deterministic candidates and offer management.
6. Remove the dead, unused route-local `ResolutionModal` from `alert/page.tsx` if it can be deleted without affecting the mounted `EmergencyResolutionModal`.
7. Remove the sidebar Emma AI link, retaining the top-toolbar Emma AI button as the single navigation entry.

## Implemented result

The visible duplication has been removed. Compliance now opens on deterministic Staffing Ratio and contains no Q&A tab. Emma AI is reachable through the single top-toolbar control and owns both Compliance Q&A and Emergency SL explanation. Alert Centre owns only the operational candidate／offer／response／manager-approval workflow. Roster now presents a four-stage generate → edit → rule-check → approve flow. Reports is the sole NAAC output workspace; it has no upload or Data Exchange section, and each report card corresponds to a NAAC workbook report sheet generated from the selected period's operative roster version.

The complete six-week, multi-sheet workbook control remains disabled and explicitly labelled as awaiting the backend golden-file implementation. The UI does not pretend that generic individual reports already satisfy the final 22-hour NAAC export acceptance criteria.
