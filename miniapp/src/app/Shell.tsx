import { Outlet } from 'react-router'
import { InviteBanner } from '../features/friends/InviteBanner'
import { TabBar } from './TabBar'

/** Bento layout shell: a scrolling column of widgets over the bottom tab bar. */
export function Shell() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 px-4 pt-[max(20px,env(safe-area-inset-top))] pb-28">
      <InviteBanner />
      <Outlet />
      <TabBar />
    </div>
  )
}
