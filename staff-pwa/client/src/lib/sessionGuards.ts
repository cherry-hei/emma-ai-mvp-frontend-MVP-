export interface CredentialSnapshot {
  generation: number;
  accessToken: string | null;
  refreshToken: string | null;
}

export function isSameCredentialSnapshot(a: CredentialSnapshot, b: CredentialSnapshot) {
  return (
    a.generation === b.generation &&
    a.accessToken === b.accessToken &&
    a.refreshToken === b.refreshToken
  );
}

/** A request remains valid only for the credential generation that started it. */
export function isCredentialGenerationCurrent(
  snapshot: CredentialSnapshot,
  currentGeneration: number,
) {
  return snapshot.generation === currentGeneration;
}
