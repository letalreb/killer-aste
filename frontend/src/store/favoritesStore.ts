import { create } from 'zustand'
import { favoritesApi } from '../api/favorites'

export interface FavoriteItem {
  id: string
  label: string       // "Milano (MI)"
  base_price?: number
  roi?: number
}

const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === 'true'

/**
 * Favorites live on the server: the backend owns the list and enforces the
 * per-user limit. This store is a cache with optimistic updates that roll
 * back if the server refuses (e.g. 409 when the limit is reached).
 */
interface FavoritesStore {
  items: FavoriteItem[]
  maxFavorites: number
  loaded: boolean
  error: string | null
  load: () => Promise<void>
  setMaxFavorites: (n: number) => void
  remove: (id: string) => Promise<void>
  toggle: (item: FavoriteItem) => Promise<void>
  has: (id: string) => boolean
  isFull: () => boolean
  clear: () => Promise<void>
  reset: () => void
}

export const useFavoritesStore = create<FavoritesStore>()((set, get) => ({
  items: [],
  maxFavorites: 3,
  loaded: false,
  error: null,

  load: async () => {
    if (SKIP_AUTH) {
      set({ loaded: true })
      return
    }
    try {
      const data = await favoritesApi.list()
      set({ items: data.items, maxFavorites: data.max_favorites, loaded: true, error: null })
    } catch {
      set({ error: 'Impossibile caricare i preferiti' })
    }
  },

  setMaxFavorites: (n) => set({ maxFavorites: n }),

  has: (id) => get().items.some((i) => i.id === id),
  isFull: () => get().items.length >= get().maxFavorites,

  remove: async (id) => {
    const previous = get().items
    set({ items: previous.filter((i) => i.id !== id), error: null })
    if (SKIP_AUTH) return
    try {
      await favoritesApi.remove(id)
    } catch {
      set({ items: previous, error: 'Impossibile rimuovere il preferito' })
    }
  },

  toggle: async (item) => {
    if (get().has(item.id)) {
      await get().remove(item.id)
      return
    }
    if (get().isFull()) return
    const previous = get().items
    set({ items: [...previous, item], error: null })
    if (SKIP_AUTH) return
    try {
      const data = await favoritesApi.add(item.id)
      set({ items: data.items, maxFavorites: data.max_favorites })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      set({
        items: previous,
        error: status === 409 ? 'Limite preferiti raggiunto' : 'Impossibile aggiungere il preferito',
      })
    }
  },

  clear: async () => {
    const previous = get().items
    set({ items: [], error: null })
    if (SKIP_AUTH) return
    try {
      await favoritesApi.clear()
    } catch {
      set({ items: previous, error: 'Impossibile svuotare i preferiti' })
    }
  },

  reset: () => set({ items: [], maxFavorites: 3, loaded: false, error: null }),
}))
