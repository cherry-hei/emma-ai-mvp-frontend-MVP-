import { apiFetch } from './api'

/**
 * Proposed facility-scoped direct-message contract.
 *
 * This helper intentionally does not add these endpoints to the shared `api`
 * object: deployment of the messaging service is still a backend dependency.
 * Calling it through `apiFetch` preserves the authenticated JWT, credential
 * generation, refresh, and tenant protections from the shared client.
 */
export interface MessageContact {
  id: string
  display_name: string
  role: string
  staff_id?: string | null
}

export interface DirectMessage {
  id: string
  sender_profile_id: string
  recipient_profile_id: string
  body: string
  created_at: string
  read_at: string | null
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isMessageContact(value: unknown): value is MessageContact {
  if (!value || typeof value !== 'object') return false
  const contact = value as Record<string, unknown>
  return nonEmptyString(contact.id) &&
    nonEmptyString(contact.display_name) &&
    nonEmptyString(contact.role) &&
    (contact.staff_id === undefined || contact.staff_id === null || typeof contact.staff_id === 'string')
}

function isDirectMessage(value: unknown): value is DirectMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Record<string, unknown>
  return nonEmptyString(message.id) &&
    nonEmptyString(message.sender_profile_id) &&
    nonEmptyString(message.recipient_profile_id) &&
    typeof message.body === 'string' &&
    nonEmptyString(message.created_at) &&
    (message.read_at === null || typeof message.read_at === 'string')
}

function contactsFrom(value: unknown): MessageContact[] {
  if (!Array.isArray(value)) throw new Error('Messages service returned an invalid contacts response.')

  // Only an identifier issued by the contacts endpoint may reach the composer.
  // Reject, rather than partially render, a malformed directory response.
  const seen = new Set<string>()
  return value.map((contact) => {
    if (!isMessageContact(contact) || seen.has(contact.id)) {
      throw new Error('Messages service returned an invalid contacts response.')
    }
    seen.add(contact.id)
    return contact
  })
}

function messagesFrom(value: unknown): DirectMessage[] {
  if (!Array.isArray(value)) throw new Error('Messages service returned an invalid conversation response.')
  if (!value.every(isDirectMessage)) throw new Error('Messages service returned an invalid conversation response.')
  return value
}

function confirmedMessage(value: unknown, operation: 'send' | 'read'): DirectMessage {
  if (!isDirectMessage(value)) {
    throw new Error(`Messages service did not return a valid ${operation} confirmation.`)
  }
  return value
}

export const messagesApi = {
  contacts: async (): Promise<MessageContact[]> => contactsFrom(await apiFetch<unknown>('/messages/contacts')),
  list: async (): Promise<DirectMessage[]> => messagesFrom(await apiFetch<unknown>('/messages')),
  send: async (recipientProfileId: string, body: string, clientMessageId?: string): Promise<DirectMessage> =>
    confirmedMessage(await apiFetch<unknown>('/messages', {
      method: 'POST',
      body: JSON.stringify({ recipient_profile_id: recipientProfileId, body,
        ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
      }),
    }), 'send'),
  markRead: async (messageId: string): Promise<DirectMessage> =>
    confirmedMessage(await apiFetch<unknown>(`/messages/${encodeURIComponent(messageId)}/read`, {
      method: 'PATCH',
    }), 'read'),
}
