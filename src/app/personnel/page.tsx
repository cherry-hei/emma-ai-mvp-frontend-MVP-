import { redirect } from 'next/navigation'

// Back-compat only: the top bar used to point here. Redirecting on the server
// avoids the blank client render during which neither nav had anything active.
export default function PersonnelPage() {
  redirect('/staff')
}
