// Single source of truth for the app's navigable routes.
//
// Sidebar and TopNav both read from here so the same screen can never be reached
// by two different paths - that split (`/personnel` on the top bar vs `/staff` on
// the sidebar) is what left the two navs highlighting different things.

import { canRead, type Feature } from '@/lib/permissions'

export const ROUTES = {
  dashboard:  '/dashboard',
  roster:     '/roster',
  scheduling: '/scheduling',
  compliance: '/compliance',
  approval:   '/approval',
  staff:      '/staff',
  roi:        '/roi',
  reports:    '/reports',
  alert:      '/alert',
  insights:   '/insights',
  settings:   '/settings',
  messages:   '/messages',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]

// Routes that render bare, without the desktop sidebar + top bar.
export const CHROMELESS: readonly string[] = ['/login', '/staff-app']

// Pure server-side redirectors. They call `redirect()` during render and never
// paint under the shell, so there is nothing to guard - and guarding them would
// only mean a role-appropriate landing decided twice.
export const REDIRECTORS: readonly string[] = ['/', '/personnel']

// Which feature each route belongs to, so menu visibility and route guarding are
// decided from the RBAC matrix rather than from a hand-kept list of roles
// (spec 1.1).
//
// This map is the whole allow-list: `isGuardedRoute` treats any screen that is
// neither chromeless nor a redirector and has no entry here as FORBIDDEN, not as
// public. Adding a page therefore has to come with a permission decision. The
// alternative fails the wrong way - `/scheduling` exists as a route on `main`
// while its `navRoutes` registration lives in a file that conflicts on merge, so
// "unmapped means open" would have published the task-scheduling screen to every
// care worker the moment those two landed together.
export const ROUTE_FEATURE: Record<string, Feature> = {
  [ROUTES.dashboard]:  'dashboard',
  [ROUTES.roster]:     'roster.view',
  [ROUTES.scheduling]: 'task_codes',
  [ROUTES.compliance]: 'compliance',
  [ROUTES.approval]:   'approve.leave',
  [ROUTES.staff]:      'staff.portfolio',
  [ROUTES.roi]:        'roi',
  [ROUTES.reports]:    'reports',
  [ROUTES.alert]:      'alerts',
  [ROUTES.settings]:   'settings',
  // PROVISIONAL: Cherry's frontend-main design has an "AI Insights" nav item and
  // route, but no page or RBAC row exists for it anywhere - not in the approved
  // RBAC matrix (permissions.ts), not on frontend-main itself. Gated on 'kpi' as
  // the closest existing analytics permission so the link doesn't 403 for
  // everyone who can already see KPIs. Needs a real decision from Cherry/the RBAC
  // spec owner once the Insights feature is actually scoped.
  [ROUTES.insights]:   'kpi',
  [ROUTES.messages]:   'approve.leave',
  '/shift-codes':      'roster.view',
}

export function routeFeature(pathname: string | null | undefined): Feature | undefined {
  if (!pathname) return undefined
  // Longest match first so `/roster/edit` resolves through `/roster`.
  const hit = Object.keys(ROUTE_FEATURE)
    .sort((a, b) => b.length - a.length)
    .find((p) => isActiveRoute(pathname, p))
  return hit ? ROUTE_FEATURE[hit] : undefined
}

/** Does this path need an RBAC decision before it may paint? */
export function isGuardedRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  if (REDIRECTORS.includes(pathname)) return false
  return !CHROMELESS.some((p) => isActiveRoute(pathname, p))
}

/** May `role` open this desktop screen?
 *
 *  Deliberately a facility-wide read, not mere visibility. A self-only (`S`)
 *  grant means "own rows in the Staff App" - the matrix writes FRONTLINE's roster
 *  cell as "- (app: own)" - so `S` must not open the desktop screen, which renders
 *  the whole home. FRONTLINE therefore holds no desktop route at all, which is
 *  what "any management feature: triple block" means. */
export function canOpenRoute(role: string | null | undefined, feature: Feature): boolean {
  return canRead(role, feature)
}

/** Where to send a user who may not see `pathname`: their first permitted screen,
 *  or the Staff App when they hold no desktop module at all (FRONTLINE). */
export function fallbackRoute(role: string | null | undefined): string {
  const first = NAV_ORDER.find((p) => canOpenRoute(role, ROUTE_FEATURE[p]))
  return first ?? '/staff-app'
}

// Menu order, also the search order for `fallbackRoute`.
const NAV_ORDER: readonly string[] = [
  ROUTES.dashboard, ROUTES.roster, ROUTES.scheduling, ROUTES.compliance,
  ROUTES.approval, ROUTES.staff, ROUTES.roi, ROUTES.reports, ROUTES.alert,
  ROUTES.insights, ROUTES.settings,
]

// Segment-aware so a path is never a prefix-match for a sibling: on `/staff-app`
// the `/staff` item must stay inactive.
export function isActiveRoute(pathname: string | null | undefined, path: string): boolean {
  if (!pathname) return false
  return pathname === path || pathname.startsWith(`${path}/`)
}

// The entry in `items` whose path matches `pathname`, or undefined when the
// current screen isn't represented in that nav (then nothing is highlighted -
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
