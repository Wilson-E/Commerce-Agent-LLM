import { Bookmark, Trash2 } from 'lucide-react'
import useSavedStore from '../stores/savedStore'
import ProductCard from '../components/product/ProductCard'

export default function SavedPage() {
  const { savedItems, clearAll } = useSavedStore()

  return (
    <div className="h-screen overflow-y-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center">
              <Bookmark size={20} className="text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">Saved Items</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {savedItems.length === 0
                  ? 'No saved items yet'
                  : `${savedItems.length} item${savedItems.length !== 1 ? 's' : ''} saved`}
              </p>
            </div>
          </div>
          {savedItems.length > 0 && (
            <button
              onClick={clearAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <Trash2 size={14} />
              Clear all
            </button>
          )}
        </div>

        {/* Empty state */}
        {savedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="h-16 w-16 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-3xl mb-4">
              🔖
            </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Nothing saved yet</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
              Click the bookmark icon on any product card to save it here for later.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {savedItems.map((product) => (
              <ProductCard key={product.id} product={product} variant="grid" />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
