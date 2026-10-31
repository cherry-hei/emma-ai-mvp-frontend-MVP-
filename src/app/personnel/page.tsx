import { redirect } from 'next/navigation'

// `/staff` is the canonical tenant-scoped Staff Portfolio.  Keep this legacy
// route server-only so a bookmarked Personnel link always receives the same
// profile/cards/filters rather than a second, drifting implementation.
export default function PersonnelPage() {
  redirect('/staff')
}
