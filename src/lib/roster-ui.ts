import type { RosterCell, ShiftDef } from '@/lib/apiTypes'

export type RosterViewMode = 'week' | 'month' | 'staff'
export type TaskTimeValidationError = 'invalid_date' | 'incomplete_time' | 'invalid_time'
export type TaskDateTimes =
  | { ok: true; startAt?: undefined; endAt?: undefined; crossesMidnight: false }
  | { ok: true; startAt: string; endAt: string; crossesMidnight: boolean }
  | { ok: false; error: TaskTimeValidationError }

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/

export function utcDate(value: string): Date | null {
  const match = ISO_DATE.exec(value)
  if (!match) return null
  const [year, month, day] = match.slice(1).map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day
    ? parsed
    : null
}

export function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10)
}

export function addUtcDays(value: string, days: number): string | null {
  const next = utcDate(value)
  if (!next) return null
  next.setUTCDate(next.getUTCDate() + days)
  return isoDate(next)
}

export function startOfUtcWeek(value: string): string | null {
  const next = utcDate(value)
  if (!next) return null
  const day = next.getUTCDay()
  next.setUTCDate(next.getUTCDate() - (day === 0 ? 6 : day - 1))
  return isoDate(next)
}

/**
 * Limits views to dates already returned by the authenticated roster endpoint.
 * `staff` is intentionally a single person's weekly view, not a different data
 * source; this keeps all modes scoped to the selected roster version and period.
 */
export function datesForRosterView(
  periodDates: string[],
  anchorDate: string,
  mode: RosterViewMode,
): string[] {
  const dates = [...new Set(periodDates)].filter((date) => utcDate(date) !== null).sort()
  if (!dates.length) return []
  const anchor = dates.includes(anchorDate) ? anchorDate : dates[0]
  if (mode === 'month') return dates.filter((date) => date.slice(0, 7) === anchor.slice(0, 7))

  const start = startOfUtcWeek(anchor)
  const end = start ? addUtcDays(start, 6) : null
  return start && end ? dates.filter((date) => date >= start && date <= end) : []
}

/**
 * `paid_minutes` is the facility/server definition. A missing, malformed, or
 * non-working value is never replaced with a guessed duration: callers render
 * unknown rather than displaying a plausible but false number of hours.
 */
export function exactPaidMinutes(cell: RosterCell | undefined, definitions: ShiftDef[]): number | null {
  if (!cell?.shift_type || !cell.is_working) return 0
  const value = definitions.find((definition) => definition.shift_type === cell.shift_type)?.paid_minutes
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
    ? value
    : null
}

export function formatExactMinutes(minutes: number): string {
  const whole = Math.max(0, Math.round(minutes))
  return `${Math.floor(whole / 60)}h ${String(whole % 60).padStart(2, '0')}m`
}

/**
 * Converts optional task times into explicit Hong Kong-offset timestamps.
 * Equal or earlier end-times explicitly roll to the next calendar day. A
 * partially supplied or invalid time is rejected before any roster write.
 */
export function taskDateTimes(date: string, start: string, end: string): TaskDateTimes {
  if (!utcDate(date)) return { ok: false, error: 'invalid_date' }
  if (!start && !end) return { ok: true, crossesMidnight: false }
  if (!start || !end) return { ok: false, error: 'incomplete_time' }
  const startMatch = HHMM.exec(start)
  const endMatch = HHMM.exec(end)
  if (!startMatch || !endMatch) return { ok: false, error: 'invalid_time' }

  const startMinutes = Number(startMatch[1]) * 60 + Number(startMatch[2])
  const endMinutes = Number(endMatch[1]) * 60 + Number(endMatch[2])
  const nextDate = endMinutes <= startMinutes ? addUtcDays(date, 1) : date
  if (!nextDate) return { ok: false, error: 'invalid_date' }

  return {
    ok: true,
    startAt: `${date}T${start}:00+08:00`,
    endAt: `${nextDate}T${end}:00+08:00`,
    crossesMidnight: nextDate !== date,
  }
}
