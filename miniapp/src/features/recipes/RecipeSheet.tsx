import { useState } from 'react'
import { useNavigate } from 'react-router'
import type { Schemas } from '../../api/client'
import { useFriends, usePlanRecipe, useRecipe, useSuggestRecipes } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Sheet } from '../../ui/Sheet'
import { PrimaryButton } from '../../ui/states'

type Meal = Schemas['Meal']
type Allergen = Schemas['Allergen']

const meals: (Meal | 'any')[] = ['any', 'breakfast', 'lunch', 'dinner', 'snack', 'dessert']
const allergens: Allergen[] = ['gluten', 'milk', 'egg', 'fish', 'shellfish', 'nuts', 'peanut', 'soy', 'sesame']

/** Cooking quest: filters, then 2-3 recipes picked by the assistant, then a plan with a friend. */
export function RecipeSheet({ onClose, recipeId }: { onClose: () => void; recipeId?: string }) {
  const [chosen, setChosen] = useState<string | null>(recipeId ?? null)
  const suggest = useSuggestRecipes()
  return (
    <Sheet title={t.recipes.title} onClose={onClose}>
      {chosen ? (
        <PlanStep recipeId={chosen} onBack={recipeId ? onClose : () => setChosen(null)} onDone={onClose} />
      ) : suggest.data ? (
        <OfferStep offer={suggest.data} onPick={setChosen} onBack={() => suggest.reset()} />
      ) : (
        <FilterStep pending={suggest.isPending} failed={suggest.isError} onFind={(body) => suggest.mutate(body)} />
      )}
    </Sheet>
  )
}

function FilterStep({ pending, failed, onFind }: { pending: boolean; failed: boolean; onFind: (body: Schemas['RecipeSuggestInput']) => void }) {
  const [meal, setMeal] = useState<Meal | 'any'>('any')
  const [vegetarian, setVegetarian] = useState(false)
  const [avoid, setAvoid] = useState<Allergen[]>([])

  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-sm font-semibold text-muted">{t.recipes.hint}</p>
      <div role="radiogroup" aria-label={t.recipes.meal} className="flex flex-wrap gap-1.5">
        {meals.map((m) => (
          <label key={m} className="flex h-10 items-center rounded-field bg-surface px-3.5 text-sm font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent has-[:focus-visible]:outline-2">
            <input type="radio" name="meal" checked={meal === m} onChange={() => setMeal(m)} className="sr-only" />
            {t.recipes.meals[m]}
          </label>
        ))}
      </div>
      <label className="flex min-h-11 items-center gap-3 text-[15px] font-bold">
        <input type="checkbox" checked={vegetarian} onChange={(e) => setVegetarian(e.target.checked)} className="size-5 accent-[var(--color-ink)]" />
        {t.recipes.vegetarian}
      </label>
      <fieldset className="m-0 flex flex-wrap gap-1.5 border-0 p-0">
        <legend className="mb-2 text-sm font-bold">{t.recipes.allergens}</legend>
        {allergens.map((a) => (
          <label key={a} className="flex h-10 items-center rounded-field bg-surface px-3.5 text-sm font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent has-[:focus-visible]:outline-2">
            <input
              type="checkbox"
              checked={avoid.includes(a)}
              onChange={(e) => setAvoid((cur) => (e.target.checked ? [...cur, a] : cur.filter((x) => x !== a)))}
              className="sr-only"
            />
            {t.recipes.allergen[a]}
          </label>
        ))}
      </fieldset>
      {failed && (
        <p role="alert" className="m-0 text-sm font-bold">
          {t.recipes.failed}
        </p>
      )}
      <PrimaryButton disabled={pending} onClick={() => onFind({ ...(meal === 'any' ? {} : { meal }), vegetarian, allergens: avoid })}>
        {t.recipes.find}
      </PrimaryButton>
    </div>
  )
}

function OfferStep({ offer, onPick, onBack }: { offer: Schemas['RecipeOffer']; onPick: (id: string) => void; onBack: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      {offer.note && <p className="m-0 rounded-card bg-surface p-4 text-sm font-bold">{offer.note}</p>}
      <ul aria-label={t.recipes.title} className="m-0 flex list-none flex-col gap-2 p-0">
        {offer.recipes.map((r) => (
          <li key={r.id} className="flex flex-col gap-2 rounded-card bg-surface p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-display text-[15px] font-bold">{r.title}</span>
              <span className="shrink-0 text-xs font-bold text-muted">{t.recipes.minutes(r.minutes)}</span>
            </div>
            {r.why && <p className="m-0 text-sm font-semibold">{r.why}</p>}
            <p className="m-0 text-xs font-bold text-muted">
              {r.allergens.length > 0 ? t.recipes.contains(r.allergens.map((a) => t.recipes.allergen[a]).join(', ')) : t.recipes.noAllergens}
            </p>
            <button type="button" aria-label={t.recipes.pick(r.title)} onClick={() => onPick(r.id)} className="h-12 rounded-[16px] bg-plate text-sm font-extrabold text-on-plate">
              {t.recipes.choose}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={onBack} className="h-11 self-start rounded-field bg-surface px-4 text-sm font-extrabold">
        {t.recipes.back}
      </button>
    </div>
  )
}

function PlanStep({ recipeId, onBack, onDone }: { recipeId: string; onBack: () => void; onDone: () => void }) {
  const navigate = useNavigate()
  const [servings, setServings] = useState(2)
  const [atHome, setAtHome] = useState<string[]>([])
  const [friendId, setFriendId] = useState<string | null>(null)
  const [shopper, setShopper] = useState<'me' | 'friend'>('me')
  const recipe = useRecipe(recipeId, servings)
  const friends = useFriends()
  const plan = usePlanRecipe()
  const detail = recipe.data
  const list = friends.data?.items ?? []

  function create() {
    if (!friendId) return
    plan.mutate(
      { recipeId, friend_id: friendId, shopper, servings, at_home: atHome },
      {
        onSuccess: (coop) => {
          haptic('success')
          onDone()
          navigate(`/coops/${coop.id}`)
        },
      },
    )
  }

  if (!detail) return <p role="status" className="m-0 text-sm font-bold text-muted">…</p>
  const title = detail.recipe.title
  const buyable = detail.lines.filter((l) => !l.staple)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="m-0 font-display text-base font-bold">{title}</h3>
        <div className="flex items-center gap-2" role="group" aria-label={t.recipes.servings}>
          <button type="button" aria-label={t.recipes.less(title)} disabled={servings <= 1} onClick={() => setServings((n) => n - 1)} className="size-11 rounded-full bg-surface text-lg font-extrabold disabled:opacity-40">
            −
          </button>
          <span aria-live="polite" className="min-w-14 text-center text-sm font-extrabold">
            {t.recipes.servings}: {servings}
          </span>
          <button type="button" aria-label={t.recipes.more(title)} disabled={servings >= 8} onClick={() => setServings((n) => n + 1)} className="size-11 rounded-full bg-surface text-lg font-extrabold">
            +
          </button>
        </div>
      </div>
      <p className="m-0 text-xs font-bold text-muted">
        {detail.recipe.allergens.length > 0 ? t.recipes.contains(detail.recipe.allergens.map((a) => t.recipes.allergen[a]).join(', ')) : t.recipes.noAllergens}. {detail.note}
      </p>

      <fieldset className="m-0 flex flex-col border-0 p-0">
        <legend className="mb-1 text-sm font-bold">{t.recipes.atHome}</legend>
        {buyable.map((l) => (
          <label key={l.ingredient} className="flex min-h-11 items-center gap-3 text-[15px] font-semibold">
            <input
              type="checkbox"
              checked={atHome.includes(l.ingredient)}
              onChange={(e) => setAtHome((cur) => (e.target.checked ? [...cur, l.ingredient] : cur.filter((x) => x !== l.ingredient)))}
              className="size-5 accent-[var(--color-ink)]"
            />
            <span>
              {l.name}: {l.amount} {l.optional ? `(${t.recipes.optional})` : ''}
            </span>
          </label>
        ))}
        {buyable.length < detail.lines.length && <p className="m-0 pt-1 text-xs font-semibold text-muted">{t.recipes.staples}</p>}
      </fieldset>

      <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend className="mb-1 text-sm font-bold">{t.recipes.withWhom}</legend>
        {friends.isSuccess && list.length === 0 && <p className="m-0 text-sm font-bold text-muted">{t.recipes.noFriends}</p>}
        {list.map((f) => (
          <label key={f.id} className="flex h-11 items-center gap-3 rounded-field bg-surface px-3 text-[15px] font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent">
            <input type="radio" name="friend" checked={friendId === f.id} onChange={() => setFriendId(f.id)} className="sr-only" />
            {f.first_name}
          </label>
        ))}
      </fieldset>

      <div role="radiogroup" aria-label={t.recipes.whoShops} className="grid grid-cols-2 gap-1.5 rounded-field bg-surface p-1">
        {(['me', 'friend'] as const).map((who) => (
          <label key={who} className="flex h-10 items-center justify-center rounded-xl text-sm font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent has-[:focus-visible]:outline-2">
            <input type="radio" name="shopper" checked={shopper === who} onChange={() => setShopper(who)} className="sr-only" />
            {who === 'me' ? t.recipes.iShop : t.recipes.friendShops}
          </label>
        ))}
      </div>
      {plan.isError && (
        <p role="alert" className="m-0 text-sm font-bold">
          {t.recipes.failed}
        </p>
      )}
      <div className="flex gap-2">
        <button type="button" onClick={onBack} className="h-14 rounded-[20px] bg-surface px-5 text-base font-extrabold">
          {t.recipes.back}
        </button>
        <PrimaryButton className="flex-1" disabled={!friendId || plan.isPending} onClick={create}>
          {t.recipes.create}
        </PrimaryButton>
      </div>
    </div>
  )
}
