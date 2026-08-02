// src/lib/rosterView.ts
//
// The API → component mapping layer for the roster calendar (task 3.1).
//
// Cherry, 1 Aug 2026: "You map the response into the shape my components expect,
// I swap the import. Clean boundary, no one touches the other's code."
//
// So this file is the boundary. `WeekView` and `KPIStrip` read `STAFF`, `ROSTER`,
// `DAYS` and `KPI` out of `@/lib/data`, the mock file. Everything below produces
// exactly those four shapes from live endpoints, and nothing below imports a
// component. The swap is:
//
//     -import { STAFF, ROSTER, DAYS } from '@/lib/data'
//     +import { useRosterView } from '@/lib/rosterView'
//     +const { staff: STAFF, roster: ROSTER, days: DAYS } = useRosterView()
//
// Two things this layer refuses to do, because both would be lies the ward acts
// on rather than bugs someone notices:
//
//   * invent a shift class for a code it cannot place. An unrecognised code
//     renders as ⚠️ with the real code under it, never as 'A'.
//   * invent a KPI. A card with no live source comes back null, so it can render
//     '—'. See `toKpiView`.
import { useCallback, useEffect, useState } from 'react'

import { api } from './api'
import type {
  ApiStaff, DashboardSummary, FacilityEvent, KpiExternalWorkforce,
  KpiStaffingRatioCompliance, KpiTaskCompletion, RosterCell, RosterGrid, ShiftDef,
} from './apiTypes'
import type { DayEntry, RosterRow, ShiftType, Staff } from './types'

// ── shift classification ────────────────────────────────────────────────────

/** Codes whose class is fixed by the two homes' dictionaries, not by the clock.
 *
 *  NAAC embeds tasks in the cell (`A7#清` = A7 + duty supervisor + cleaning) and
 *  Salvation Army does not (`A1`, `A2N`), but both write the shift itself first,
 *  so a prefix match over this table places most cells without a lookup.
 */
const EXACT: Record<string, ShiftType> = {
  A: 'A', B: 'B', E: 'E', P: 'P', N: 'N', AN: 'AN',
  OFF: 'OFF', O: 'OFF', DO: 'OFF', PH: 'OFF', X: 'OFF',
  AL: 'AL', SL: 'AL', CL: 'AL', ML: 'AL', NPL: 'AL',
  S: 'SLEEP', SLEEP: 'SLEEP', SLP: 'SLEEP',
}

/** The task and meal marks NAAC writes into the same cell as the shift. */
const TASK_MARKS = /[#^*清藥]/gu
const MEAL_CODE = /([<>]\d{1,4})/

/** `A7#清` → { code: 'A7', marks: '#清' }; `P2 >1` → { code: 'P2', meal: '>1' } */
export function splitCell(raw: string): { code: string; marks: string; meal?: string } {
  const text = String(raw || '').trim()
  const meal = text.match(MEAL_CODE)?.[1]
  const withoutMeal = meal ? text.replace(meal, '') : text
  const marks = withoutMeal.match(TASK_MARKS)?.join('') ?? ''
  const code = withoutMeal.replace(TASK_MARKS, '').replace(/\s+/g, '').toUpperCase()
  return { code, marks, meal }
}

function hourOf(time?: string | null): number | null {
  if (!time) return null
  const h = Number(String(time).slice(0, 2))
  return Number.isFinite(h) ? h : null
}

/** Classify by the facility's own shift dictionary — clock times, not spelling. */
function classifyByDefinition(def: ShiftDef): ShiftType {
  if (!def.is_working) return 'OFF'
  // A split shift with a night leg is an A/N however it is spelled. The backend
  // models these as `segments`; one leg starting in the morning and another
  // after 19:00 is the Code of Practice A/N shift.
  const legs = def.segments ?? []
  if (legs.length > 1) {
    const starts = legs.map(l => hourOf(l.start)).filter((h): h is number => h !== null)
    if (starts.some(h => h < 12) && starts.some(h => h >= 19)) return 'AN'
  }
  const start = hourOf(def.start_time)
  if (start === null) return 'A'
  if (def.cross_midnight && start >= 19) return 'N'
  if (start < 12) return 'A'
  if (start < 19) return 'P'
  return 'N'
}

/**
 * The shift class for one cell, given the facility's shift dictionary.
 *
 * Order matters: the dictionary wins over the prefix heuristic, because the
 * dictionary is configuration the home controls and the heuristic is our guess
 * about their spelling. `A3` at Salvation Army is an afternoon duty despite
 * starting with A, and only the dictionary knows that.
 */
export function classifyShift(
  raw: string | null | undefined,
  defs: Map<string, ShiftDef>,
): ShiftType | null {
  const { code } = splitCell(raw ?? '')
  if (!code) return null

  const def = defs.get(code)
  if (def) return classifyByDefinition(def)

  if (EXACT[code]) return EXACT[code]
  // A code ending in N that begins with a morning duty is the A/N split -
  // A1N, A2N, A3N at Salvation Army, AN at NAAC.
  if (/^[A0-9]+N$/.test(code)) return 'AN'
  if (/^(7A|9A|LA|A\d*)$/.test(code)) return 'A'
  if (/^(7P|9P|LP|P\d*)$/.test(code)) return 'P'
  if (/^N\d*$/.test(code)) return 'N'
  // Deliberately not a guess. Painting an unplaceable code 'A' tells the ward a
  // night nurse is on the morning shift; ⚠️ with the code beneath it tells the
  // truth, and tells the scheduler their dictionary is missing a row.
  return 'ALERT'
}

function toDayEntry(cell: RosterCell, defs: Map<string, ShiftDef>): DayEntry {
  const raw = cell.shift_type ?? ''
  const { code, marks, meal } = splitCell(raw)
  const type = classifyShift(raw, defs) ?? (cell.is_working ? 'ALERT' : 'OFF')
  const entry: DayEntry = { type }
  // The original cell, kept verbatim - the printed roster is checked against the
  // workbook, and '7A' must not come back as 'A'.
  if (code) entry.shiftLabel = code
  if (meal) entry.mealCode = meal
  if (cell.tasks?.length) entry.tasks = cell.tasks
  if (marks) entry.note = marks
  return entry
}

// ── staff and rows ──────────────────────────────────────────────────────────

/** `Staff` as the components declare it, plus the uuid writes need. */
export type MappedStaff = Staff & { uuid: string }
export type MappedRosterRow = RosterRow & { staffUuid: string }

export interface RosterView {
  staff: MappedStaff[]
  roster: MappedRosterRow[]
  days: string[]
  dates: string[]
  events: FacilityEvent[]
  versionId: string | null
  periodId: string | null
  status: string | null
}

const WEEKDAY_EN = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const WEEKDAY_ZH = ['日', '一', '二', '三', '四', '五', '六']

/** '2026-08-03' → 'MON 3/8' / '一 3/8', matching the mock's `DAYS` strings. */
export function toDayLabel(iso: string, lang: 'zh' | 'en' = 'en'): string {
  const [y, m, d] = iso.split('-').map(Number)
  const weekday = new Date(Date.UTC(y, (m || 1) - 1, d || 1)).getUTCDay()
  const name = lang === 'zh' ? WEEKDAY_ZH[weekday] : WEEKDAY_EN[weekday]
  return `${name} ${d}/${m}`
}

/**
 * The grid names every staff member it rosters; `/staff` carries the rest of the
 * card - certificates, and hours worked against hours contracted.
 *
 * Passing `staffList` is optional so the calendar still renders when that call
 * has not resolved (or 403s for a role that may see the roster and not the
 * portfolio). Without it the hours bar reads 0 of 0, which the component already
 * handles, rather than the page failing to paint.
 */
export function toRosterView(
  grid: RosterGrid,
  staffList: ApiStaff[] = [],
  shiftDefs: ShiftDef[] = [],
  lang: 'zh' | 'en' = 'en',
): RosterView {
  const defs = new Map(shiftDefs.map(d => [d.shift_type.toUpperCase(), d]))
  const detail = new Map(staffList.map(s => [s.id, s]))

  const staff: MappedStaff[] = grid.rows.map((row, i) => {
    const extra = detail.get(row.staff.id)
    return {
      // The components key on a number and the API on a uuid. The index is a
      // render key, not an identity: `uuid` is what any write must send back.
      id: i + 1,
      uuid: row.staff.id,
      name: row.staff.name,
      nameEn: row.staff.name_en ?? '',
      role: row.staff.rank,
      ward: row.staff.unit_name ?? extra?.unit_name ?? '',
      floor: row.staff.unit_name ?? '',
      certs: extra?.certs ?? [],
      hoursWorked: Math.round(extra?.scheduled_hours ?? 0),
      hoursTotal: Math.round(extra?.contracted_period_hours ?? 0),
      avatar: (row.staff.name || row.staff.name_en || '?').trim().charAt(0),
    }
  })

  // One cell per date in `grid.dates`, in that order, so column N of every row
  // is the same day. A row missing a date gets an empty cell rather than a
  // shorter array - a short row would slide every later shift left by one day.
  const byDate = (cells: RosterCell[]) => new Map(cells.map(c => [c.date, c]))
  const roster: MappedRosterRow[] = grid.rows.map((row, i) => {
    const cells = byDate(row.cells)
    return {
      staffId: i + 1,
      staffUuid: row.staff.id,
      days: grid.dates.map(date => {
        const cell = cells.get(date)
        return cell ? toDayEntry(cell, defs) : { type: 'OFF' as ShiftType }
      }),
    }
  })

  return {
    staff,
    roster,
    days: grid.dates.map(d => toDayLabel(d, lang)),
    dates: grid.dates,
    events: grid.events ?? [],
    versionId: grid.version_id ?? null,
    periodId: grid.period_id ?? null,
    status: grid.status ?? null,
  }
}

export const EMPTY_ROSTER_VIEW: RosterView = {
  staff: [], roster: [], days: [], dates: [], events: [],
  versionId: null, periodId: null, status: null,
}

// ── the hook the components swap their import for ───────────────────────────

export interface UseRosterView extends RosterView {
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Live roster for one period. Omit `periodId` and it uses the current period
 * from `/roster-periods`, which is what the calendar page wants on first paint.
 */
export function useRosterView(opts?: {
  periodId?: string
  versionId?: string
  lang?: 'zh' | 'en'
}): UseRosterView {
  const { periodId, versionId, lang = 'en' } = opts ?? {}
  const [nonce, setNonce] = useState(0)
  // One state object keyed by the request that produced it. `loading` is then
  // derived - `state.key !== key` - rather than flipped by a setState in the
  // effect body, which React 19 flags as a cascading render.
  const [state, setState] = useState<{
    key: string; view: RosterView; error: string | null
  } | null>(null)

  const key = JSON.stringify([periodId ?? null, versionId ?? null, lang, nonce])
  const reload = useCallback(() => setNonce(n => n + 1), [setNonce])

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      let view = EMPTY_ROSTER_VIEW
      let error: string | null = null
      try {
        let id = periodId
        if (!id) {
          const periods = await api.rosterPeriods()
          id = periods[0]?.id
        }
        if (id) {
          const grid = await api.rosterGrid(id, { versionId })
          // The supporting calls only enrich the grid, so one of them failing
          // must not blank the calendar.
          const [staffList, shiftDefs] = await Promise.all([
            api.listStaff().catch(() => [] as ApiStaff[]),
            api.shiftDefinitions().catch(() => [] as ShiftDef[]),
          ])
          view = toRosterView(grid, staffList, shiftDefs, lang)
        }
      } catch (e) {
        error = e instanceof Error ? e.message : String(e)
      }
      if (!cancelled) setState({ key, view, error })
    })()

    return () => { cancelled = true }
  }, [key, periodId, versionId, lang])

  return {
    ...(state?.view ?? EMPTY_ROSTER_VIEW),
    loading: state?.key !== key,
    error: state?.key === key ? state.error : null,
    reload,
  }
}

// ── KPIStrip ────────────────────────────────────────────────────────────────

/**
 * The five cards `KPIStrip` renders. `null` means "no live source yet" - the
 * card should show '—'.
 *
 * Three of the five map onto something the backend actually measures. Two do
 * not, and are left null rather than filled with a plausible number:
 *
 *   otHours       there is no OT figure for the operative roster. The optimiser
 *                 reports OT per candidate option (`KpiSummary.ot_hours`), which
 *                 is a projection for a draft, not hours anyone has worked.
 *                 Cherry confirmed on 2 Aug 2026 that a dash here is fine for now.
 *
 * `completion` was the fifth. It is live as of 2 Aug 2026: Cherry settled the
 * ambiguity as task completion - "% of assigned tasks marked done per shift" -
 * which `GET /kpi/overview` now reports as `task_completion`. It stays null when
 * the period rosters no task codes, because a home with nothing to tick has not
 * failed to tick it.
 *
 * `staffingRatio` is the SWD ratio-compliance pass rate, not the mock's '1:20'
 * literal - a home has one ratio rule per rank and window, so a single ratio
 * string cannot be true. The pass rate is the honest one-number summary.
 */
export interface KpiView {
  staffingRatio: string | null
  emergencyResponseTime: string | null
  otHours: number | null
  otDelta: number | null
  agencyShifts: number | null
  agencyDelta: number | null
  completion: number | null
}

export const EMPTY_KPI_VIEW: KpiView = {
  staffingRatio: null, emergencyResponseTime: null, otHours: null,
  otDelta: null, agencyShifts: null, agencyDelta: null, completion: null,
}

export function toKpiView(
  dashboard?: DashboardSummary | null,
  externalWorkforce?: Partial<KpiExternalWorkforce> | null,
  ratioCompliance?: Partial<KpiStaffingRatioCompliance> | null,
  taskCompletion?: Partial<KpiTaskCompletion> | null,
): KpiView {
  const pct = (v: number | undefined | null) =>
    typeof v === 'number' ? `${Math.round(v)}%` : null
  return {
    staffingRatio: pct(ratioCompliance?.pass_rate_pct),
    emergencyResponseTime: pct(dashboard?.kpis?.auto_resolved_pct),
    otHours: null,
    otDelta: null,
    agencyShifts: externalWorkforce?.agency_shifts ?? null,
    agencyDelta: null,
    completion: typeof taskCompletion?.completion_pct === 'number'
      ? Math.round(taskCompletion.completion_pct)
      : null,
  }
}

export interface UseKpiView extends KpiView {
  loading: boolean
  error: string | null
}

/** The KPI strip's live figures. `KPIStrip` swaps `import { KPI }` for this. */
export function useKpiView(periodId?: string): UseKpiView {
  const [state, setState] = useState<{
    key: string; kpi: KpiView; error: string | null
  } | null>(null)
  const key = periodId ?? ''

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      // Two independent sources, and a role may hold one and not the other -
      // `dashboard` and `kpi` are separate rows of the permission matrix. One
      // 403 must blank its own cards, not all five.
      const [dashboard, overview] = await Promise.all([
        api.dashboard().catch(() => null),
        api.kpiOverview(periodId).catch(() => null),
      ])
      if (cancelled) return
      setState({
        key,
        kpi: toKpiView(dashboard, overview?.external_workforce,
                       overview?.staffing_ratio_compliance,
                       overview?.task_completion),
        error: !dashboard && !overview
          ? 'KPIs are unavailable for this account' : null,
      })
    })()

    return () => { cancelled = true }
  }, [key, periodId])

  return {
    ...(state?.kpi ?? EMPTY_KPI_VIEW),
    loading: state?.key !== key,
    error: state?.key === key ? state.error : null,
  }
}
