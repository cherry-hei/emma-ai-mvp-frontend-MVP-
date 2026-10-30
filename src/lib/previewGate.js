/**
 * A public, build-time gate for the externally shared integration preview.
 *
 * The preview is deliberately not connected to the current API because its
 * authentication/RLS posture has not been accepted for that environment.
 */
export const PREVIEW_NETWORK_DISABLED_MESSAGE =
  'Integration preview: sign-in and server requests are disabled.'

export function isIntegrationPreview() {
  return process.env.NEXT_PUBLIC_INTEGRATION_PREVIEW === '1'
}

/** Throw before an API client can read, attach, or send credentials. */
export function assertPreviewNetworkAllowed() {
  if (isIntegrationPreview()) {
    throw new Error(PREVIEW_NETWORK_DISABLED_MESSAGE)
  }
}
