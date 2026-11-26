import { adminRequest } from './adminResources'

export function aiOperation<T>(path: string, method = 'GET', body?: object) {
  return adminRequest<T>(`/ai${path}`, {
    method,
    ...(body && { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
  })
}
