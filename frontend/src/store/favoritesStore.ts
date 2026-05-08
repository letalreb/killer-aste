import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const MAX_FAVORITES = 3

export interface FavoriteItem {
  id: string
  label: string       // "Milano (MI)"
  base_price?: number
  roi?: number
}

interface FavoritesStore {
  items: FavoriteItem[]
  add: (item: FavoriteItem) => boolean   // false = already full
  remove: (id: string) => void
  toggle: (item: FavoriteItem) => boolean  // returns new isFavorite state
  has: (id: string) => boolean
  isFull: () => boolean
  clear: () => void
}

export const useFavoritesStore = create<FavoritesStore>()(
  persist(
    (set, get) => ({
      items: [],

      has: (id) => get().items.some((i) => i.id === id),
      isFull: () => get().items.length >= MAX_FAVORITES,

      add: (item) => {
        if (get().isFull()) return false
        if (get().has(item.id)) return true
        set((s) => ({ items: [...s.items, item] }))
        return true
      },

      remove: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),

      toggle: (item) => {
        if (get().has(item.id)) {
          get().remove(item.id)
          return false
        }
        return get().add(item)
      },

      clear: () => set({ items: [] }),
    }),
    { name: 'killer-aste-favorites' }
  )
)
