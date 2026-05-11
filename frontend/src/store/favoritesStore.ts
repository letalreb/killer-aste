import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface FavoriteItem {
  id: string
  label: string       // "Milano (MI)"
  base_price?: number
  roi?: number
}

interface FavoritesStore {
  items: FavoriteItem[]
  maxFavorites: number
  setMaxFavorites: (n: number) => void
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
      maxFavorites: 3,

      setMaxFavorites: (n) => set({ maxFavorites: n }),

      has: (id) => get().items.some((i) => i.id === id),
      isFull: () => get().items.length >= get().maxFavorites,

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
    {
      name: 'killer-aste-favorites',
      partialize: (s) => ({ items: s.items, maxFavorites: s.maxFavorites }),
    }
  )
)
