import type { Schemas } from '../../api/client'
import { formatNumber, t } from '../../i18n'
import { Icon } from '../../ui/Icon'

type Entry = Schemas['LadderEntry']

function name(e: Entry): string {
  return e.is_me ? t.friends.me : e.user.first_name
}

/** Podium for the top three (1st in the middle and tallest), then a list (US-16). */
export function Ladder({ entries }: { entries: Entry[] }) {
  const [first, second, third] = entries
  const rest = entries.slice(3)
  return (
    <>
      <ol aria-label={t.friends.title} className="m-0 grid list-none grid-cols-3 items-end gap-2 p-0">
        {second && <Podium entry={second} height="h-[150px]" />}
        {first && <Podium entry={first} height="h-[186px]" leader />}
        {third && <Podium entry={third} height="h-[128px]" />}
      </ol>
      {rest.length > 0 && (
        <ol className="m-0 flex list-none flex-col rounded-card bg-surface px-4 py-1.5">
          {rest.map((e) => (
            <li
              key={e.user.id}
              aria-label={`${t.friends.rank(e.rank)}: ${name(e)}, ${formatNumber(e.points)}`}
              className={`flex h-13 items-center gap-3 border-t border-bg first:border-t-0 ${e.is_me ? 'font-extrabold' : ''}`}
            >
              <span className="w-6 font-display text-sm font-bold text-muted">{e.rank}</span>
              <span className="flex-1 truncate text-[15px] font-bold">{name(e)}</span>
              <span className="text-xs font-bold text-muted">{t.friends.streak(e.streak_days)}</span>
              <span className={`w-14 text-right text-[15px] font-extrabold ${e.is_me ? 'rounded-lg bg-accent px-1.5 text-on-accent' : ''}`}>{formatNumber(e.points)}</span>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}

function Podium({ entry, height, leader = false }: { entry: Entry; height: string; leader?: boolean }) {
  const tone = entry.is_me ? 'bg-accent text-on-accent' : leader ? 'bg-plate text-on-plate' : 'bg-surface text-ink'
  return (
    <li
      aria-label={`${t.friends.rank(entry.rank)}: ${name(entry)}, ${formatNumber(entry.points)}`}
      className={`flex ${height} flex-col justify-between rounded-3xl p-3 ${tone}`}
    >
      <span className="flex items-center justify-between">
        <span className={`font-display text-[22px] font-extrabold ${leader && !entry.is_me ? 'text-accent' : ''}`}>{entry.rank}</span>
        {leader && <Icon name="crown" size={22} className={entry.is_me ? '' : 'text-accent'} />}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-[15px] font-extrabold">{name(entry)}</span>
        <span className="text-[13px] font-bold opacity-75">{formatNumber(entry.points)}</span>
      </span>
    </li>
  )
}
