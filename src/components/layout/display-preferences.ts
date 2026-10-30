export const DISPLAY_TEXT_SCALES = [100, 125, 150, 200] as const

export type DisplayTextScale = (typeof DISPLAY_TEXT_SCALES)[number]
export type ScrollPosition = { top: number; left: number }
export type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export const DISPLAY_PREFERENCES_STORAGE_KEY = 'emma:manager:display-preferences'
export const VIEW_POSITIONS_STORAGE_KEY = 'emma:manager:view-positions'

const MAX_STORED_PATHS = 24
const MAX_SCROLL_OFFSET = 10_000_000

/**
 * These helpers retain only user-interface preferences. They never receive,
 * inspect, or persist identity, facility, roster, or API-response data.
 */
export function clampTextScale(value: unknown): DisplayTextScale {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return 100

  const bounded = Math.min(200, Math.max(100, numeric))
  return DISPLAY_TEXT_SCALES.reduce<DisplayTextScale>((closest, candidate) => (
    Math.abs(candidate - bounded) < Math.abs(closest - bounded) ? candidate : closest
  ), 100)
}

export function readDisplayTextScale(storage?: StorageLike | null): DisplayTextScale {
  const value = readJson(storage, DISPLAY_PREFERENCES_STORAGE_KEY)
  return isRecord(value) ? clampTextScale(value.textScale) : 100
}

export function saveDisplayTextScale(scale: unknown, storage?: StorageLike | null): DisplayTextScale {
  const textScale = clampTextScale(scale)
  writeJson(storage, DISPLAY_PREFERENCES_STORAGE_KEY, { textScale })
  return textScale
}

export function applyDisplayTextScale(scale: unknown, root?: HTMLElement | null): DisplayTextScale {
  const textScale = clampTextScale(scale)
  const target = root ?? (typeof document === 'undefined' ? null : document.documentElement)
  if (target) {
    target.style.setProperty('--emma-text-scale', String(textScale / 100))
    target.dataset.emmaTextScale = String(textScale)
  }
  return textScale
}

export function readPageViewPosition(pathname: string, storage?: StorageLike | null): ScrollPosition | null {
  const path = normalizePathname(pathname)
  if (!path) return null
  return readViewPositions(storage)[path] ?? null
}

export function savePageViewPosition(pathname: string, position: ScrollPosition, storage?: StorageLike | null): void {
  const path = normalizePathname(pathname)
  const normalized = sanitizeScrollPosition(position)
  if (!path || !normalized) return

  const positions = readViewPositions(storage)
  // Re-inserting an existing path makes it most-recent before bounded trimming.
  delete positions[path]
  positions[path] = normalized
  for (const oldest of Object.keys(positions).slice(0, -MAX_STORED_PATHS)) delete positions[oldest]
  writeJson(storage, VIEW_POSITIONS_STORAGE_KEY, positions)
}

export function normalizePathname(value: unknown): string | null {
  if (typeof value !== 'string' || !value.startsWith('/') || value.length > 200) return null
  const pathname = value.split(/[?#]/, 1)[0]
  return pathname && !/\s/.test(pathname) ? pathname : null
}

function readViewPositions(storage?: StorageLike | null): Record<string, ScrollPosition> {
  const value = readJson(storage, VIEW_POSITIONS_STORAGE_KEY)
  if (!isRecord(value)) return {}

  return Object.entries(value).reduce<Record<string, ScrollPosition>>((positions, [path, position]) => {
    const normalizedPath = normalizePathname(path)
    const normalizedPosition = sanitizeScrollPosition(position)
    if (normalizedPath && normalizedPosition) positions[normalizedPath] = normalizedPosition
    return positions
  }, {})
}

function sanitizeScrollPosition(value: unknown): ScrollPosition | null {
  if (!isRecord(value)) return null
  const top = normalizeScrollOffset(value.top)
  const left = normalizeScrollOffset(value.left)
  return top === null || left === null ? null : { top, left }
}

function normalizeScrollOffset(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.min(MAX_SCROLL_OFFSET, Math.max(0, numeric))
}

function readJson(storage: StorageLike | null | undefined, key: string): unknown {
  const target = resolveStorage(storage)
  if (!target) return null
  try {
    const raw = target.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeJson(storage: StorageLike | null | undefined, key: string, value: unknown): void {
  const target = resolveStorage(storage)
  if (!target) return
  try {
    target.setItem(key, JSON.stringify(value))
  } catch {
    // Private browsing, quota exhaustion, or blocked storage must not break UI.
  }
}

function resolveStorage(storage: StorageLike | null | undefined): StorageLike | null {
  if (storage !== undefined) return storage
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
