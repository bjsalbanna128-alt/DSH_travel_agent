export const LOGIN_SESSION_KEY = 'travel_login_session'

export interface LoginSession {
  accountId: string
  id: string
}

export function randomSessionId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),
    byte => byte.toString(16).padStart(2, '0')).join('')
}

export function readLoginSession(): LoginSession | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(LOGIN_SESSION_KEY) || 'null')
    if (typeof value?.accountId === 'string' && /^[0-9a-f]{32}$/.test(value?.id)) return value
  } catch { /* Session frequency control requires accessible browser storage. */ }
}

export function saveLoginSession(value?: LoginSession) {
  try {
    if (value) localStorage.setItem(LOGIN_SESSION_KEY, JSON.stringify(value))
    else localStorage.removeItem(LOGIN_SESSION_KEY)
    return true
  } catch {
    return false
  }
}

function openStore(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('travel-recommendation-sessions', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('sessions')
    request.onerror = () => reject(request.error)
    request.onsuccess = () => resolve(request.result)
  })
}

async function transact<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore, setResult: (value: T) => void, transaction: IDBTransaction) => void,
): Promise<T> {
  const db = await openStore()
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = db.transaction('sessions', mode)
      let result: T
      transaction.oncomplete = () => resolve(result)
      transaction.onabort = () => reject(transaction.error)
      work(transaction.objectStore('sessions'), value => { result = value }, transaction)
    })
  } finally {
    db.close()
  }
}

export function recoverLegacySession(accountId: string) {
  return transact<string>('readwrite', (store, result) => {
    const key = `legacy:${accountId}`
    const get = store.get(key)
    get.onsuccess = () => {
      if (typeof get.result === 'string') {
        result(get.result)
      } else {
        const id = randomSessionId()
        store.add(id, key)
        result(id)
      }
    }
  })
}

function shownKey(session: LoginSession) {
  return `shown:${JSON.stringify([session.accountId, session.id])}`
}

export async function recommendationWasShown(session: LoginSession) {
  try {
    return await transact<boolean>('readonly', (store, result) => {
      const get = store.get(shownKey(session))
      get.onsuccess = () => result(Boolean(get.result))
    })
  } catch {
    return true
  }
}

export async function showRecommendationOnce(
  session: LoginSession, eligible: () => boolean, open: () => void,
) {
  try {
    const key = shownKey(session)
    const owner = randomSessionId()
    const won = await transact<boolean>('readwrite', (store, result, transaction) => {
      result(false)
      if (!eligible()) return
      const add = store.add(owner, key)
      add.onsuccess = () => {
        if (eligible()) result(true)
        else transaction.abort()
      }
      add.onerror = event => {
        if (add.error?.name === 'ConstraintError') {
          event.preventDefault()
          event.stopPropagation()
        }
      }
    })
    if (!won) return
    if (eligible()) {
      open()
    } else {
      await transact<void>('readwrite', (store) => {
        const get = store.get(key)
        get.onsuccess = () => { if (get.result === owner) store.delete(key) }
      })
    }
  } catch { /* Fail closed when the browser cannot record a display. */ }
}
