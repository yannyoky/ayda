package app.ayda.android.ui.recipes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.api.models.Allergen
import app.ayda.api.models.Coop
import app.ayda.api.models.Meal
import app.ayda.api.models.RecipeCard
import app.ayda.api.models.RecipeLine
import app.ayda.api.models.RecipePlanInput
import app.ayda.shared.recipes.RecipeStep
import app.ayda.shared.recipes.RecipesViewModel

@Composable
private fun Meal.label(): String =
    stringResource(
        when (this) {
            Meal.breakfast -> R.string.recipes_meal_breakfast
            Meal.lunch -> R.string.recipes_meal_lunch
            Meal.dinner -> R.string.recipes_meal_dinner
            Meal.snack -> R.string.recipes_meal_snack
            Meal.dessert -> R.string.recipes_meal_dessert
        },
    )

@Composable
private fun Allergen.label(): String =
    stringResource(
        when (this) {
            Allergen.gluten -> R.string.recipes_allergen_gluten
            Allergen.milk -> R.string.recipes_allergen_milk
            Allergen.egg -> R.string.recipes_allergen_egg
            Allergen.fish -> R.string.recipes_allergen_fish
            Allergen.shellfish -> R.string.recipes_allergen_shellfish
            Allergen.nuts -> R.string.recipes_allergen_nuts
            Allergen.peanut -> R.string.recipes_allergen_peanut
            Allergen.soy -> R.string.recipes_allergen_soy
            Allergen.sesame -> R.string.recipes_allergen_sesame
        },
    )

@Composable
private fun RecipeLine.Unit.label(): String =
    stringResource(
        when (this) {
            RecipeLine.Unit.g -> R.string.recipes_unit_g
            RecipeLine.Unit.ml -> R.string.recipes_unit_ml
            RecipeLine.Unit.pcs -> R.string.recipes_unit_pcs
            RecipeLine.Unit.clove -> R.string.recipes_unit_clove
            RecipeLine.Unit.slice -> R.string.recipes_unit_slice
            RecipeLine.Unit.tbsp -> R.string.recipes_unit_tbsp
            RecipeLine.Unit.tsp -> R.string.recipes_unit_tsp
            RecipeLine.Unit.pinch -> R.string.recipes_unit_pinch
        },
    )

@Composable
private fun RecipeCard.allergenLine(): String =
    if (allergens.isEmpty()) {
        stringResource(R.string.recipes_no_allergens)
    } else {
        val names = allergens.map { it.label() }
        stringResource(R.string.recipes_contains, names.joinToString(", "))
    }

private fun Double.pretty(): String = if (this % 1.0 == 0.0) toLong().toString() else "%.1f".format(this)

/** Cooking quest: filters, then 2-3 recipes picked by the assistant, then a plan with a friend. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipeSheet(
    model: RecipesViewModel,
    onClose: () -> Unit,
    onCreated: (Coop) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    ModalBottomSheet(onDismissRequest = onClose, containerColor = LocalAydaColors.current.bg) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(stringResource(R.string.recipes_title), style = MaterialTheme.typography.headlineSmall)
            when (state.step) {
                RecipeStep.Filters -> Filters(model)
                RecipeStep.Offer -> Offer(model)
                RecipeStep.Plan -> PlanStep(model, onCreated)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Filters(model: RecipesViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    Text(stringResource(R.string.recipes_hint), style = MaterialTheme.typography.bodyMedium, color = colors.muted)
    Text(stringResource(R.string.recipes_meal), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Chip(stringResource(R.string.recipes_meal_any), state.meal == null, radio = true) { model.setMeal(null) }
        Meal.entries.forEach { meal -> Chip(meal.label(), state.meal == meal, radio = true) { model.setMeal(meal) } }
    }
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .toggleable(state.vegetarian, role = Role.Checkbox) { model.setVegetarian(it) },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Checkbox(checked = state.vegetarian, onCheckedChange = null)
        Text(stringResource(R.string.recipes_vegetarian), style = MaterialTheme.typography.bodyLarge)
    }
    Text(stringResource(R.string.recipes_allergens), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Allergen.entries.forEach { a -> Chip(a.label(), a in state.avoid, radio = false) { model.toggleAllergen(a) } }
    }
    state.error?.let { Text(stringResource(R.string.recipes_failed), style = MaterialTheme.typography.labelLarge) }
    PrimaryButton(stringResource(R.string.recipes_find), onClick = model::find, enabled = !state.loading)
}

@Composable
private fun Chip(
    text: String,
    on: Boolean,
    radio: Boolean,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val modifier =
        Modifier
            .heightIn(min = 40.dp)
            .background(if (on) colors.accent else colors.surface, MaterialTheme.shapes.medium)
    Row(
        (
            if (radio) {
                modifier.selectable(on, role = Role.RadioButton, onClick = onClick)
            } else {
                modifier.toggleable(on, role = Role.Checkbox) { onClick() }
            }
        ).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (on) colors.onAccent else colors.ink)
    }
}

@Composable
private fun Offer(model: RecipesViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val offer = state.offer ?: return
    offer.note?.let { Card { Text(it, style = MaterialTheme.typography.labelLarge) } }
    offer.recipes.forEach { recipe ->
        Card {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(recipe.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(
                    stringResource(R.string.recipes_minutes, recipe.minutes),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            }
            recipe.why?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Text(recipe.allergenLine(), style = MaterialTheme.typography.labelLarge, color = colors.muted)
            PrimaryButton(stringResource(R.string.recipes_choose), onClick = { model.choose(recipe.id) })
        }
    }
    state.error?.let { Text(stringResource(R.string.recipes_failed), style = MaterialTheme.typography.labelLarge) }
    TextButton(onClick = model::back) { Text(stringResource(R.string.recipes_back)) }
}

@Composable
private fun PlanStep(
    model: RecipesViewModel,
    onCreated: (Coop) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val detail = state.detail
    if (detail == null) {
        state.error?.let { Text(stringResource(R.string.recipes_failed), style = MaterialTheme.typography.labelLarge) }
        TextButton(onClick = model::back) { Text(stringResource(R.string.recipes_back)) }
        return
    }
    val buyable = detail.lines.filter { !it.staple }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(detail.recipe.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        TextButton(
            onClick = { model.setServings(state.servings - 1) },
            enabled = state.servings > 1,
        ) { Text("−") }
        Text(stringResource(R.string.recipes_servings, state.servings), style = MaterialTheme.typography.labelLarge)
        TextButton(
            onClick = { model.setServings(state.servings + 1) },
            enabled = state.servings < RecipesViewModel.MAX_SERVINGS,
        ) { Text("+") }
    }
    Text(
        detail.recipe.allergenLine() + ". " + detail.note,
        style = MaterialTheme.typography.labelLarge,
        color = colors.muted,
    )
    Text(stringResource(R.string.recipes_at_home), style = MaterialTheme.typography.labelLarge)
    buyable.forEach { line ->
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 48.dp)
                .toggleable(
                    line.ingredient in state.atHome,
                    role = Role.Checkbox,
                ) { model.toggleAtHome(line.ingredient) },
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Checkbox(checked = line.ingredient in state.atHome, onCheckedChange = null)
            Text(
                "${line.name}: ${line.amount.pretty()} ${line.unit.label()}" +
                    if (line.optional) " (${stringResource(R.string.recipes_optional)})" else "",
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
    if (buyable.size < detail.lines.size) {
        Text(
            stringResource(R.string.recipes_staples),
            style = MaterialTheme.typography.labelLarge,
            color = colors.muted,
        )
    }
    Text(stringResource(R.string.recipes_with_whom), style = MaterialTheme.typography.labelLarge)
    if (state.friends.isEmpty()) {
        Text(
            stringResource(R.string.recipes_no_friends),
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
    }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        state.friends.forEach { f ->
            Chip(f.firstName, state.friendId == f.id, radio = true) { model.pickFriend(f.id) }
        }
    }
    Text(stringResource(R.string.recipes_who_shops), style = MaterialTheme.typography.labelLarge)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Chip(stringResource(R.string.recipes_i_shop), state.shopper == RecipePlanInput.Shopper.me, radio = true) {
            model.setShopper(RecipePlanInput.Shopper.me)
        }
        Chip(
            stringResource(R.string.recipes_friend_shops),
            state.shopper == RecipePlanInput.Shopper.friend,
            radio = true,
        ) {
            model.setShopper(RecipePlanInput.Shopper.friend)
        }
    }
    state.error?.let { Text(stringResource(R.string.recipes_failed), style = MaterialTheme.typography.labelLarge) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        TextButton(onClick = model::back) { Text(stringResource(R.string.recipes_back)) }
        PrimaryButton(
            stringResource(R.string.recipes_create),
            onClick = { model.create(onCreated) },
            enabled = state.canCreate,
            modifier = Modifier.weight(1f),
        )
    }
}
