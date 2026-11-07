/** Memory-only retry keys. Never retain chat bodies across logout or tenants. */
export class MessageSendAttempts {
  private pending = new Map<string, { body: string; key: string }>()
  private nextKey: () => string

  constructor(nextKey: () => string = () => crypto.randomUUID()) {
    this.nextKey = nextKey
  }

  keyFor(contactId: string, body: string): string {
    const current = this.pending.get(contactId)
    if (current?.body === body) return current.key
    const key = this.nextKey()
    this.pending.set(contactId, { body, key })
    return key
  }

  discardIfChanged(contactId: string, body: string): void {
    if (this.pending.get(contactId)?.body !== body) this.pending.delete(contactId)
  }

  confirmed(contactId: string): void {
    this.pending.delete(contactId)
  }

  reset(): void {
    this.pending.clear()
  }
}
