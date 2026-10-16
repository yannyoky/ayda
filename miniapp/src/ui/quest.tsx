import type { Schemas } from '../api/client'
import { Icon, type IconName } from './Icon'

const categoryIcon: Record<Schemas['Category'], IconName> = {
  sport: 'sport',
  walk: 'walk',
  city: 'city',
  rest: 'rest',
  project: 'project',
  social: 'social',
  home: 'home',
  learning: 'learning',
}

export function CategoryIcon({ category, dark = false }: { category: Schemas['Category']; dark?: boolean }) {
  return (
    <span className={`flex size-11 shrink-0 items-center justify-center rounded-tile ${dark ? 'bg-plate text-on-plate' : 'bg-bg text-ink'}`}>
      <Icon name={categoryIcon[category]} size={20} />
    </span>
  )
}
