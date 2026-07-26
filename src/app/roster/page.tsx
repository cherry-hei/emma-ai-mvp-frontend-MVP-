import { RealRosterBoard } from '@/components/roster/RealRosterBoard'

// Real, backend-driven roster: period + version selection, live grid, manual cell
// edit, the CP-SAT A/B/C solver (AI Roster Suggest), validation and publish — all
// against the FastAPI API (RLS-scoped to the signed-in facility). The previous
// mock/NAAC prototype lived here; see git history for that demo UI.
export default function RosterPage() {
  return <RealRosterBoard />
}
