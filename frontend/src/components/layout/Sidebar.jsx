import { useNavigate, useLocation } from 'react-router-dom'
import {
  Sparkles, Home, Bookmark, ShoppingCart,
  User, Settings, HelpCircle, LogOut,
} from 'lucide-react'
import useAuthStore from '../../stores/authStore'
import useCartStore from '../../stores/cartStore'
import useSavedStore from '../../stores/savedStore'

function SidebarBtn({ icon: Icon, label, onClick, active, badge }) {
  return (
    <button
      title={label}
      onClick={onClick}
      className={`relative w-10 h-10 rounded-xl flex items-center justify-center transition-all group ${
        active
          ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400'
          : 'text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-800 dark:hover:text-gray-200'
      }`}
    >
      <Icon size={20} />
      {badge > 0 && (
        <span className="absolute -top-1 -right-1 bg-indigo-500 text-white text-[9px] font-bold rounded-full h-4 w-4 flex items-center justify-center leading-none">
          {badge > 9 ? '9+' : badge}
        </span>
      )}
      {/* Tooltip */}
      <span className="pointer-events-none absolute left-full ml-3 px-2 py-1 rounded-md bg-gray-900 dark:bg-gray-700 text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-[60]">
        {label}
      </span>
    </button>
  )
}

export default function Sidebar({ activePanel, setActivePanel }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { logout } = useAuthStore()
  const { toggleCart, itemCount } = useCartStore()
  const savedCount = useSavedStore((s) => s.savedItems.length)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  function togglePanel(panel) {
    setActivePanel((prev) => (prev === panel ? null : panel))
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-16 bg-white dark:bg-gray-950 border-r border-gray-200 dark:border-gray-800 flex flex-col items-center py-4 z-40 shadow-sm">
      {/* Logo */}
      <button
        onClick={() => { navigate('/'); setActivePanel(null) }}
        className="h-10 w-10 rounded-xl bg-gradient-to-r from-indigo-600 to-sky-600 text-white flex items-center justify-center shadow-sm mb-6 hover:opacity-90 transition-opacity"
        title="ShopAssist"
      >
        <Sparkles size={18} />
      </button>

      {/* Main nav */}
      <nav className="flex-1 flex flex-col items-center gap-1.5">
        <SidebarBtn
          icon={Home}
          label="Home"
          onClick={() => { navigate('/'); setActivePanel(null) }}
          active={location.pathname === '/' && activePanel === null}
        />
        <SidebarBtn
          icon={Bookmark}
          label="Saved"
          onClick={() => { navigate('/saved'); setActivePanel(null) }}
          active={location.pathname === '/saved' && activePanel === null}
          badge={savedCount}
        />
        <SidebarBtn
          icon={ShoppingCart}
          label="Cart"
          onClick={toggleCart}
          badge={itemCount}
        />
        <SidebarBtn
          icon={User}
          label="Profile"
          onClick={() => togglePanel('profile')}
          active={activePanel === 'profile'}
        />
        <SidebarBtn
          icon={Settings}
          label="Settings"
          onClick={() => togglePanel('settings')}
          active={activePanel === 'settings'}
        />
      </nav>

      {/* Bottom */}
      <div className="flex flex-col items-center gap-1.5">
        <SidebarBtn icon={HelpCircle} label="Help" onClick={() => {}} />
        <SidebarBtn icon={LogOut} label="Sign out" onClick={handleLogout} />
      </div>
    </aside>
  )
}
