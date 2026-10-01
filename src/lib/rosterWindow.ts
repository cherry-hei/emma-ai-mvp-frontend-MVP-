// Pure view projection over the backend roster grid. Never mutates roster data.
export type RosterWindowMode = 'WEEK_ALL' | 'MONTH_ALL' | 'STAFF'

export function isoAddDays(iso: string, offset: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  const stamp = Date.UTC(year, month - 1, day + offset)
  return new Date(stamp).toISOString().slice(0, 10)
}

export function weekStart(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay()
  return isoAddDays(iso, -(day + 6) % 7)
}

export function moveWindow(iso: string, mode: RosterWindowMode, direction: -1 | 1): string {
  if (mode !== 'MONTH_ALL') return isoAddDays(iso, 7 * direction)
  const [year, month] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1 + direction, 1)).toISOString().slice(0, 10)
}

/** Intersect the UI window with the selected period: no invented outside dates. */
export function windowDates(dates: string[], mode: RosterWindowMode, focusDate: string): string[] {
  if (!focusDate) return dates
  if (mode === 'MONTH_ALL') return dates.filter(date => date.slice(0, 7) === focusDate.slice(0, 7))
  const first = weekStart(focusDate)
  const last = isoAddDays(first, 6)
  return dates.filter(date => date >= first && date <= last)
}
