import { NavLink } from 'react-router'
import { useConversations } from '../api/queries'
import { t } from '../i18n'
import { useRealtimeStatus } from '../realtime/realtime'
import { haptic } from '../telegram/webapp'
import { Icon, type IconName } from '../ui/Icon'

const tabs: { to: string; icon: IconName; label: string }[] = [
  { to: '/', icon: 'today', label: t.nav.today },
  { to: '/feed', icon: 'feed', label: t.nav.feed },
  { to: '/chats', icon: 'chat', label: t.nav.chats },
  { to: '/friends', icon: 'friends', label: t.nav.friends },
  { to: '/profile', icon: 'profile', label: t.nav.profile },
]

export function TabBar() {
  const realtime = useRealtimeStatus()
  const conversations = useConversations({ poll: realtime !== 'live' })
  const unread = conversations.data?.items.reduce((sum, c) => sum + c.unread_count, 0) ?? 0
  return (
    <nav
      aria-label={t.nav.label}
      className="fixed inset-x-4 bottom-[max(16px,env(safe-area-inset-bottom))] z-20 mx-auto flex h-16 max-w-[480px] items-center justify-around rounded-bar bg-plate px-2 shadow-[0_8px_24px_rgb(0_0_0/0.18)]"
    >
      {tabs.map((tab) => {
        const badge = tab.to === '/chats' && unread > 0
        const label = badge ? t.nav.chatsUnread(unread) : tab.label
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/'}
            aria-label={label}
            onClick={() => haptic('tap')}
            className={({ isActive }) =>
              isActive
                ? 'flex h-12 items-center gap-1.5 rounded-full bg-accent px-4 text-sm font-extrabold text-on-accent no-underline'
                : 'relative flex size-12 items-center justify-center rounded-full text-on-plate'
            }
          >
            {({ isActive }) => (
              <>
                <Icon name={tab.icon} size={isActive ? 20 : 22} />
                {isActive && <span>{tab.label}</span>}
                {badge && !isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute top-1.5 right-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[11px] font-extrabold text-on-accent"
                  >
                    {unread > 99 ? '99+' : unread}
                  </span>
                )}
              </>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
