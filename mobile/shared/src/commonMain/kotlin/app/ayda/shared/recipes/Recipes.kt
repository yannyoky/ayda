package app.ayda.shared.recipes

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Allergen
import app.ayda.api.models.Coop
import app.ayda.api.models.DayQuest
import app.ayda.api.models.Friend
import app.ayda.api.models.Meal
import app.ayda.api.models.RecipeDetail
import app.ayda.api.models.RecipeOffer
import app.ayda.api.models.RecipePlanInput
import app.ayda.api.models.RecipeQuestInput
import app.ayda.api.models.RecipeSuggestInput
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class RecipeStep { Filters, Offer, Plan }

data class RecipesState(
    val step: RecipeStep = RecipeStep.Filters,
    val meal: Meal? = null,
    val vegetarian: Boolean = false,
    val avoid: Set<Allergen> = emptySet(),
    val loading: Boolean = false,
    val offer: RecipeOffer? = null,
    val detail: RecipeDetail? = null,
    val servings: Int = RecipesViewModel.DEFAULT_SERVINGS,
    val atHome: Set<String> = emptySet(),
    val friends: List<Friend> = emptyList(),
    val friendId: String? = null,
    val shopper: RecipePlanInput.Shopper = RecipePlanInput.Shopper.me,
    val creating: Boolean = false,
    val error: String? = null,
) {
    /** Cooking alone needs no friend (ADR 0014); [friendId] makes it a plan with one. */
    val canCreate: Boolean get() = detail != null && !creating
}

/**
 * A cooking quest (M5, ADR 0012 and 0014): a recipe from the assistant, then either an own quest
 * for today or a plan where one friend shops and the other cooks.
 */
class RecipesViewModel(
    private val client: AydaClient,
) : ViewModel() {
    private val mutableState = MutableStateFlow(RecipesState())
    val state: StateFlow<RecipesState> = mutableState.asStateFlow()

    fun setMeal(meal: Meal?) = mutableState.update { it.copy(meal = meal) }

    fun setVegetarian(on: Boolean) = mutableState.update { it.copy(vegetarian = on) }

    fun toggleAllergen(allergen: Allergen) =
        mutableState.update { it.copy(avoid = if (allergen in it.avoid) it.avoid - allergen else it.avoid + allergen) }

    fun find() {
        val current = state.value
        if (current.loading) return
        mutableState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val body =
                RecipeSuggestInput(
                    meal = current.meal,
                    allergens = current.avoid.toList(),
                    vegetarian = current.vegetarian,
                )
            val found = apiCall { client.recipes.suggestRecipes(body) }
            mutableState.update {
                if (found is ApiResult.Ok) {
                    it.copy(loading = false, offer = found.value, step = RecipeStep.Offer)
                } else {
                    it.copy(loading = false, error = found.errorText())
                }
            }
        }
    }

    fun choose(recipeId: String) {
        mutableState.update {
            it.copy(
                step = RecipeStep.Plan,
                detail = null,
                atHome = emptySet(),
                servings = DEFAULT_SERVINGS,
                error = null,
            )
        }
        viewModelScope.launch {
            loadDetail(recipeId, DEFAULT_SERVINGS)
            if (state.value.friends.isEmpty()) {
                val friends = apiCall { client.social.listFriends() }
                if (friends is ApiResult.Ok) mutableState.update { it.copy(friends = friends.value.items) }
            }
        }
    }

    fun back() =
        mutableState.update {
            when (it.step) {
                // A recipe opened straight from the assistant chat has no offer to go back to
                RecipeStep.Plan if it.offer == null -> it.copy(step = RecipeStep.Filters, detail = null, error = null)
                RecipeStep.Plan -> it.copy(step = RecipeStep.Offer, detail = null, error = null)
                else -> it.copy(step = RecipeStep.Filters, offer = null, error = null)
            }
        }

    fun setServings(servings: Int) {
        val id =
            state.value.detail
                ?.recipe
                ?.id ?: return
        val clamped = servings.coerceIn(1, MAX_SERVINGS)
        mutableState.update { it.copy(servings = clamped) }
        viewModelScope.launch { loadDetail(id, clamped) }
    }

    fun toggleAtHome(ingredient: String) =
        mutableState.update {
            it.copy(
                atHome =
                    if (ingredient in
                        it.atHome
                    ) {
                        it.atHome - ingredient
                    } else {
                        it.atHome + ingredient
                    },
            )
        }

    fun pickFriend(friendId: String?) = mutableState.update { it.copy(friendId = friendId) }

    fun setShopper(shopper: RecipePlanInput.Shopper) = mutableState.update { it.copy(shopper = shopper) }

    fun create(
        onCooking: (DayQuest) -> Unit,
        onCreated: (Coop) -> Unit,
    ) {
        val current = state.value
        val detail = current.detail
        if (!current.canCreate || detail == null) return
        val friendId = current.friendId
        mutableState.update { it.copy(creating = true, error = null) }
        viewModelScope.launch {
            if (friendId == null) {
                val body = RecipeQuestInput(servings = current.servings, atHome = current.atHome.toList())
                val cooking = apiCall { client.recipes.cookRecipeQuest(detail.recipe.id, body) }
                mutableState.update {
                    it.copy(creating = false, error = if (cooking is ApiResult.Ok) null else cooking.errorText())
                }
                if (cooking is ApiResult.Ok) onCooking(cooking.value)
                return@launch
            }
            val body =
                RecipePlanInput(
                    friendId = friendId,
                    shopper = current.shopper,
                    servings = current.servings,
                    atHome = current.atHome.toList(),
                )
            val created = apiCall { client.recipes.planRecipe(detail.recipe.id, body) }
            mutableState.update {
                it.copy(
                    creating = false,
                    error = if (created is ApiResult.Ok) null else created.errorText(),
                )
            }
            if (created is ApiResult.Ok) onCreated(created.value)
        }
    }

    private suspend fun loadDetail(
        recipeId: String,
        servings: Int,
    ) {
        val loaded = apiCall { client.recipes.getRecipe(recipeId, servings) }
        mutableState.update {
            if (loaded is ApiResult.Ok) it.copy(detail = loaded.value) else it.copy(error = loaded.errorText())
        }
    }

    companion object {
        const val DEFAULT_SERVINGS = 2
        const val MAX_SERVINGS = 8
    }
}
