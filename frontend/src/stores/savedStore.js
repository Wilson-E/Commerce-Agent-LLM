import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const useSavedStore = create(
  persist(
    (set, get) => ({
      savedItems: [],

      saveItem: (product) => {
        if (!get().savedItems.find((p) => p.id === product.id)) {
          set((s) => ({ savedItems: [...s.savedItems, { ...product, savedAt: Date.now() }] }))
        }
      },

      unsaveItem: (productId) => {
        set((s) => ({ savedItems: s.savedItems.filter((p) => p.id !== productId) }))
      },

      isSaved: (productId) => get().savedItems.some((p) => p.id === productId),

      clearAll: () => set({ savedItems: [] }),
    }),
    { name: 'shopassist-saved' }
  )
)

export default useSavedStore
