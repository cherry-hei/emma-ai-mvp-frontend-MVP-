// Single source of truth for the app's navigable routes.
//
// Sidebar and TopNav both read from here so the same screen can never be reached
// by two different paths — that split (`/personnel` on the top bar vs `/staff` on
// the sidebar) is what left the two navs highlighting different things.

export const ROUTES = {
  dashboard:  '/dashboard',
  roster:     '/roster',
  compliance: '/compliance',
  approval:   '/approval',
  staff:      '/staff',
  roi:        '/roi',
  reports:    '/reports',
  alert:      '/alert',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]

// Routes that render bare, without the desktop sidebar + top bar.
export const CHROMELESS: readonly string[] = ['/login', '/staff-app']

// Segment-aware so a path is never a prefix-match for a sibling: on `/staff-app`
// the `/staff` item must stay inactive.
export function isActiveRoute(pathname: string | null | undefined, path: string): boolean {
  if (!pathname) return false
  return pathname === path || pathname.startsWith(`${path}/`)
}

// The entry in `items` whose path matches `pathname`, or undefined when the
// current screen isn't represented in that nav (then nothing is highlighted —
// better than leaving a stale tab lit).
export function activeItem<T extends { path: string }>(
  items: readonly T[],
  pathname: string | null | undefined,
): T | undefined {
  // Longest path first, so `/roster/edit` prefers `/roster/edit` over `/roster`.
  return [...items]
    .sort((a, b) => b.path.length - a.path.length)
    .find((item) => isActiveRoute(pathname, item.path))
}
