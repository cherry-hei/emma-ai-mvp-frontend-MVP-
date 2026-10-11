// Single source of truth for the app's navigable routes. Sidebar and TopNav read
// from here so route visibility and route guarding stay aligned.

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

/**
 * Desktop navigation only. Shift Dictionary and Task Scheduling remain routable
 * for old deep links, but live under Settings so the sidebar has one clear
 * operational hierarchy. Settings is intentionally last, below Emma AI.
 */
export const SIDEBAR_NAVIGATION = [
  { key: 'nav_dashboard',  icon: '🏠',  path: ROUTES.dashboard },
  { key: 'nav_roster',     icon: '📅',  path: ROUTES.roster },
  { key: 'nav_compliance', icon: '✅',  path: ROUTES.compliance },
  { key: 'nav_approval',   icon: '👥✓', path: ROUTES.approval },
  { key: 'nav_personnel',  icon: '👤',  path: ROUTES.staff },
  { key: 'nav_reports',    icon: '📊',  path: ROUTES.reports },
  { key: 'nav_alert',      icon: '🔔',  path: ROUTES.alert },
  { key: 'nav_ai',         icon: '✦',   path: ROUTES.insights },
  { key: 'nav_messages',   icon: '💬',  path: ROUTES.messages },
  { key: 'nav_settings',   icon: '⚙️',  path: ROUTES.settings },
] as const

// Routes that render bare, without the desktop sidebar + top bar.
export const CHROMELESS: readonly string[] = ['/login', '/staff-app']

// Pure server-side redirectors. They call redirect() during render and never
// paint under the shell, so there is nothing to guard here.
export const REDIRECTORS: readonly string[] = ['/', '/personnel']

// This map is the route allow-list. An unmapped desktop screen is forbidden,
// never default-public.
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
  [ROUTES.settings]:   'roster.view', // container only; each child retains its own original grant
  // The Emma AI workspace is management-only and reuses existing `kpi` read
  // permission until the backend defines a dedicated AI capability.
  [ROUTES.insights]:   'kpi',
  [ROUTES.messages]:   'approve.leave',
  // Compatibility route only; its content is embedded under Settings as well.
  '/shift-codes':      'roster.view',
}

export function routeFeature(pathname: string | null | undefined): Feature | undefined {
  if (!pathname) return undefined
  const hit = Object.keys(ROUTE_FEATURE)
    .sort((a, b) => b.length - a.length)
    .find((path) => isActiveRoute(pathname, path))
  return hit ? ROUTE_FEATURE[hit] : undefined
}

/** Does this path need an RBAC decision before it may paint? */
export function isGuardedRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  if (REDIRECTORS.includes(pathname)) return false
  return !CHROMELESS.some((path) => isActiveRoute(pathname, path))
}

/**
 * May `role` open this desktop screen? Self-only grants intentionally do not
 * open facility-wide management screens.
 */
export function canOpenRoute(role: string | null | undefined, feature: Feature): boolean {
  return canRead(role, feature)
}

/** Send a denied user to their first permitted desktop screen, or the Staff App. */
export function fallbackRoute(role: string | null | undefined): string {
  const first = NAV_ORDER.find((path) => canOpenRoute(role, ROUTE_FEATURE[path]))
  return first ?? '/staff-app'
}

const NAV_ORDER: readonly string[] = SIDEBAR_NAVIGATION.map((item) => item.path)

// Segment-aware so /staff-app never lights /staff.
export function isActiveRoute(pathname: string | null | undefined, path: string): boolean {
  if (!pathname) return false
  return pathname === path || pathname.startsWith(`${path}/`)
}

export function activeItem<T extends { path: string }>(
  items: readonly T[],
  pathname: string | null | undefined,
): T | undefined {
  return [...items]
    .sort((a, b) => b.path.length - a.path.length)
    .find((item) => isActiveRoute(pathname, item.path))
}
