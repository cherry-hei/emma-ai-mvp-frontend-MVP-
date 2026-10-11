import { apiFetch } from './api'

/** Shared contract with the Staff App for same-facility direct messages. */
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

/**
 * Keep this surface separate from api.ts so it inherits apiFetch's credential-
 * generation refresh safety rather than duplicating auth or token storage.
 */
export const messagesApi = {
  contacts: () => apiFetch<MessageContact[]>('/messages/contacts'),
  list: () => apiFetch<DirectMessage[]>('/messages'),
  send: (recipientProfileId: string, body: string) =>
    apiFetch<DirectMessage>('/messages', {
      method: 'POST',
      body: JSON.stringify({ recipient_profile_id: recipientProfileId, body }),
    }),
  markRead: (messageId: string) =>
    apiFetch<DirectMessage>(`/messages/${encodeURIComponent(messageId)}/read`, {
      method: 'PATCH',
    }),
}
