import type { RouteLocationRaw } from 'vue-router'
import type { InboxMessage } from './types/support'

export function notificationDestination(message: InboxMessage): RouteLocationRaw {
  switch (message.target_type) {
    case 'admin_ticket':
      return { name: 'admin-ticket-detail', params: { id: message.target_id } }
    case 'tourist_ticket':
      return {
        name: 'my-ticket-detail', params: { id: message.target_id },
        query: { round: message.target_version?.toString() },
      }
    case 'trip_confirmation':
      return { name: 'admin-message-detail', params: { id: message.id } }
  }
}
