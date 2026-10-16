import { NavLink } from 'react-router'
import { t } from '../i18n'
import { haptic } from '../telegram/webapp'
import { Icon, type IconName } from '../ui/Icon'

const tabs: { to: string; icon: IconName; label: string }[] = [
  { to: '/', icon: 'today', label: t.nav.today },
  { to: '/feed', icon: 'feed', label: t.nav.feed },
  { to: '/friends', icon: 'friends', label: t.nav.friends },
  { to: '/profile', icon: 'profile', label: t.nav.profile },
]

export function TabBar() {
  return (
    <nav
      aria-label={t.nav.label}
      className="fixed inset-x-4 bottom-[max(16px,env(safe-area-inset-bottom))] z-20 mx-auto flex h-16 max-w-[480px] items-center justify-around rounded-bar bg-plate px-2 shadow-[0_8px_24px_rgb(0_0_0/0.18)]"
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          aria-label={tab.label}
          onClick={() => haptic('tap')}
          className={({ isActive }) =>
            isActive
              ? 'flex h-12 items-center gap-1.5 rounded-3xl bg-accent px-4 text-sm font-extrabold text-on-accent no-underline'
              : 'flex size-12 items-center justify-center rounded-3xl text-on-plate'
          }
        >
          {({ isActive }) => (
            <>
              <Icon name={tab.icon} size={isActive ? 20 : 22} />
              {isActive && <span>{tab.label}</span>}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
