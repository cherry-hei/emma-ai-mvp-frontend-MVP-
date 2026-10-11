import type { RosterCell, ShiftDef } from '@/lib/apiTypes'

export type RosterViewMode = 'week' | 'month' | 'staff'

export type TaskTimeValidationError = 'invalid_date' | 'incomplete_time' | 'invalid_time'

export type TaskDateTimes =
  | { ok: true; startAt?: undefined; endAt?: undefined; crossesMidnight: false }
  | { ok: true; startAt: string; endAt: string; crossesMidnight: boolean }
  | { ok: false; error: TaskTimeValidationError }

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/

/**
 * Build task timestamps without relying on the browser's local timezone. A task
 * whose end is the same as or earlier than its start explicitly ends next day.
 * Blank start/end means "no task timing"; a one-sided or malformed value is not
 * serialised because it would create an ambiguous task row.
 */
export function taskDateTimes(date: string, start: string, end: string): TaskDateTimes {
  const dateParts = ISO_DATE.exec(date)
  if (!dateParts) return { ok: false, error: 'invalid_date' }
  const [year, month, day] = dateParts.slice(1).map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    return { ok: false, error: 'invalid_date' }
  }
  if (!start && !end) return { ok: true, crossesMidnight: false }
  if (!start || !end) return { ok: false, error: 'incomplete_time' }
  const startParts = HHMM.exec(start)
  const endParts = HHMM.exec(end)
  if (!startParts || !endParts) return { ok: false, error: 'invalid_time' }
  const startMinutes = Number(startParts[1]) * 60 + Number(startParts[2])
  const endMinutes = Number(endParts[1]) * 60 + Number(endParts[2])
  const endDate = endMinutes <= startMinutes ? addUtcDays(date, 1) : date
  return {
    ok: true,
    startAt: `${date}T${start}:00+08:00`,
    endAt: `${endDate}T${end}:00+08:00`,
    crossesMidnight: endDate !== date,
  }
}

export function utcDate(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

export function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10)
}

export function addUtcDays(value: string, days: number): string {
  const next = utcDate(value)
  next.setUTCDate(next.getUTCDate() + days)
  return isoDate(next)
}

export function startOfUtcWeek(value: string): string {
  const next = utcDate(value)
  const day = next.getUTCDay()
  next.setUTCDate(next.getUTCDate() - (day === 0 ? 6 : day - 1))
  return isoDate(next)
}

/** Uses only dates already supplied by the authenticated organisation roster. */
export function datesForRosterView(
  periodDates: string[],
  anchorDate: string,
  mode: RosterViewMode,
): string[] {
  const sorted = [...new Set(periodDates)].sort()
  if (!sorted.length) return []
  if (mode === 'staff') return sorted.filter((date) => {
    const start = startOfUtcWeek(anchorDate)
    const end = addUtcDays(start, 6)
    return date >= start && date <= end
  })
  if (mode === 'week') {
    const start = startOfUtcWeek(anchorDate)
    const end = addUtcDays(start, 6)
    return sorted.filter((date) => date >= start && date <= end)
  }
  const month = anchorDate.slice(0, 7)
  return sorted.filter((date) => date.slice(0, 7) === month)
}

/**
 * `paid_minutes` is the server/facility shift-definition value. Never infer from
 * elapsed start/end times: cross-midnight and unpaid breaks make that unsafe.
 */
export function exactPaidMinutes(cell: RosterCell | undefined, definitions: ShiftDef[]): number | null {
  if (!cell?.shift_type || !cell.is_working) return 0
  const value = definitions.find((definition) => definition.shift_type === cell.shift_type)?.paid_minutes
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
}

export function formatExactMinutes(minutes: number): string {
  const whole = Math.max(0, Math.round(minutes))
  return `${Math.floor(whole / 60)}h ${String(whole % 60).padStart(2, '0')}m`
}
