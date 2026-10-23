import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useCookRecipeQuest, useFriends, usePlanRecipe, useRecipe } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Sheet } from '../../ui/Sheet'
import { PrimaryButton } from '../../ui/states'

/** A cooking quest from a recipe the assistant picked: alone by default, or with a friend (ADR 0014). */
export function RecipeSheet({ onClose, recipeId }: { onClose: () => void; recipeId: string }) {
  return (
    <Sheet title={t.recipes.title} onClose={onClose}>
      <PlanStep recipeId={recipeId} onBack={onClose} onDone={onClose} />
    </Sheet>
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
  const solo = useCookRecipeQuest()
  const detail = recipe.data
  const list = friends.data?.items ?? []
  const pending = plan.isPending || solo.isPending

  function create() {
    if (!friendId) {
      solo.mutate(
        { recipeId, servings, at_home: atHome },
        {
          onSuccess: () => {
            haptic('success')
            onDone()
            navigate('/')
          },
        },
      )
      return
    }
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
        <label className="flex h-11 items-center gap-3 rounded-field bg-surface px-3 text-[15px] font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent">
          <input type="radio" name="friend" checked={friendId === null} onChange={() => setFriendId(null)} className="sr-only" />
          {t.recipes.alone}
        </label>
        {list.map((f) => (
          <label key={f.id} className="flex h-11 items-center gap-3 rounded-field bg-surface px-3 text-[15px] font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent">
            <input type="radio" name="friend" checked={friendId === f.id} onChange={() => setFriendId(f.id)} className="sr-only" />
            {f.first_name}
          </label>
        ))}
      </fieldset>

      {friendId && (
        <div role="radiogroup" aria-label={t.recipes.whoShops} className="grid grid-cols-2 gap-1.5 rounded-field bg-surface p-1">
          {(['me', 'friend'] as const).map((who) => (
            <label key={who} className="flex h-10 items-center justify-center rounded-xl text-sm font-bold has-[:checked]:bg-accent has-[:checked]:text-on-accent has-[:focus-visible]:outline-2">
              <input type="radio" name="shopper" checked={shopper === who} onChange={() => setShopper(who)} className="sr-only" />
              {who === 'me' ? t.recipes.iShop : t.recipes.friendShops}
            </label>
          ))}
        </div>
      )}
      {(plan.isError || solo.isError) && (
        <p role="alert" className="m-0 text-sm font-bold">
          {t.recipes.failed}
        </p>
      )}
      <div className="flex gap-2">
        <button type="button" onClick={onBack} className="h-14 rounded-[20px] bg-surface px-5 text-base font-extrabold">
          {t.recipes.back}
        </button>
        <PrimaryButton className="flex-1" disabled={pending} onClick={create}>
          {friendId ? t.recipes.create : t.recipes.addQuest}
        </PrimaryButton>
      </div>
    </div>
  )
}
