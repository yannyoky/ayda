import { useId, useState } from 'react'
import type { Schemas } from '../../api/client'
import { useCitySearch } from '../../api/queries'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'

type Coords = { lat: number; lon: number }

/** City by name or by a one-time geolocation; coordinates go to the lookup only and are never kept. */
export function CityPicker({ selected, onPick }: { selected: Schemas['City'] | null; onPick: (city: Schemas['City']) => void }) {
  const inputId = useId()
  const [query, setQuery] = useState('')
  const [coords, setCoords] = useState<Coords | undefined>()
  const [locating, setLocating] = useState(false)
  const [locateFailed, setLocateFailed] = useState(false)
  const search = useCitySearch(coords ? coords : { query })
  const items = search.data?.items ?? []
  const searching = coords !== undefined || query.trim().length >= 2

  function locate() {
    if (!navigator.geolocation) {
      setLocateFailed(true)
      return
    }
    setLocating(true)
    setLocateFailed(false)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        // Two decimals (~1 km) is plenty to find the settlement
        setCoords({ lat: Math.round(pos.coords.latitude * 100) / 100, lon: Math.round(pos.coords.longitude * 100) / 100 })
      },
      () => {
        setLocating(false)
        setLocateFailed(true)
      },
      { maximumAge: 600_000, timeout: 10_000 },
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <label htmlFor={inputId} className="sr-only">
        {t.onboarding.city.search}
      </label>
      <input
        id={inputId}
        type="search"
        autoComplete="off"
        value={query}
        placeholder={t.onboarding.city.searchPlaceholder}
        onChange={(e) => {
          setQuery(e.target.value)
          setCoords(undefined)
        }}
        className="h-12 rounded-field border-0 bg-surface px-4 text-[15px] font-semibold text-ink placeholder:text-muted"
      />
      <button
        type="button"
        onClick={locate}
        disabled={locating}
        className="flex h-12 items-center justify-center gap-2 rounded-field bg-plate text-[15px] font-extrabold text-on-plate disabled:opacity-60"
      >
        <Icon name="pin" size={18} />
        {locating ? t.onboarding.city.locating : t.onboarding.city.locate}
      </button>
      {locateFailed && <p className="m-0 text-sm font-semibold text-muted">{t.onboarding.city.locateFailed}</p>}
      {searching && search.isSuccess && items.length === 0 && (
        <p className="m-0 text-sm font-semibold text-muted">{t.onboarding.city.nothingFound}</p>
      )}
      {searching && items.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 rounded-card bg-surface p-2">
          {items.map((city) => {
            const active = selected?.id === city.id
            return (
              <li key={city.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => onPick(city)}
                  className={`flex w-full items-center justify-between gap-3 rounded-field px-3 py-2.5 text-left ${active ? 'bg-accent text-on-accent' : 'bg-transparent text-ink'}`}
                >
                  <span className="flex flex-col">
                    <span className="text-[15px] font-bold">{city.name}</span>
                    <span className={`text-xs font-semibold ${active ? '' : 'text-muted'}`}>{city.region_name}</span>
                  </span>
                  {active && <Icon name="check" size={18} strokeWidth={2.6} />}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {selected && !items.some((c) => c.id === selected.id) && (
        <div className="flex items-center justify-between rounded-field bg-surface px-4 py-3">
          <span className="flex flex-col">
            <span className="text-xs font-bold text-muted">{t.onboarding.city.selected}</span>
            <span className="text-[15px] font-bold">{selected.name}</span>
          </span>
          <Icon name="check" size={18} strokeWidth={2.6} />
        </div>
      )}
    </div>
  )
}
