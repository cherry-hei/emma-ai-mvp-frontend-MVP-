/**
 * Formats persisted minute values for people. Persistence remains integer minutes;
 * this is presentation only. Missing, invalid, or negative values are unknown—not
 * zero—and therefore render as an em dash.
 */
export function formatHoursMinutes(minutes: number | null | undefined, lang: 'en' | 'zh' = 'en'): string {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes) || minutes < 0) return '—'

  const wholeMinutes = Math.round(minutes)
  const hours = Math.floor(wholeMinutes / 60)
  const remainder = wholeMinutes % 60

  return lang === 'zh'
    ? `${hours}小時${remainder}分`
    : `${hours}h${String(remainder).padStart(2, '0')}m`
}
