package app.ayda.shared.recipes

import app.ayda.api.models.Allergen
import app.ayda.api.models.Meal
import app.ayda.api.models.RecipePlanInput
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.bodyText
import app.ayda.shared.json
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class RecipesTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun card() =
        """{"id":"pancakes","title":"Блины на молоке","meal":"breakfast","minutes":35,"servings":2,""" +
            """"allergens":["egg","gluten","milk"],"vegetarian":true,"why":"Просто и вкусно"}"""

    private fun detail(servings: Int) =
        """{"recipe":${card()},"servings":$servings,"lines":[""" +
            """{"ingredient":"flour","name":"Мука","amount":${75 * servings},"unit":"g","aisle":"grocery",""" +
            """"optional":false,"staple":false}],"steps":["Взбить яйца."],"note":"Проверяй состав."}"""

    private fun coop() =
        """{"id":"k1","title":"Готовим: Блины","category":"home","duration_min":75,""" +
            """"owner":{"id":"me","first_name":"Я"},""" +
            """"my_status":"owner","participants":[],"my_quest_id":null,"conversation_id":null,""" +
            """"expires_at":"2026-10-24T01:00:00Z","bonus_awarded":false}"""

    private fun client(): AydaClient {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@RecipesTest.dispatcher
                    addHandler { request ->
                        val call = "${request.method.value} ${request.url.encodedPath.removePrefix("/api/v1")}"
                        calls += "$call ${request.url.encodedQuery} ${request.bodyText()}".trim()
                        when (call) {
                            "POST /recipes/suggest" -> json("""{"source":"llm","recipes":[${card()}],"note":null}""")
                            "GET /recipes/pancakes" ->
                                json(detail(request.url.parameters["servings"]?.toInt() ?: 2))
                            "GET /friends" ->
                                json("""{"items":[{"id":"lena","first_name":"Лена","since":"2026-10-01T00:00:00Z"}]}""")
                            "POST /recipes/pancakes/plan" -> json(coop(), HttpStatusCode.Created)
                            else -> error("unexpected $call")
                        }
                    }
                },
            )
        return AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
    }

    @Test
    fun filtersGoToTheServerAndTheOfferComesBack() =
        runTest(dispatcher) {
            val model = RecipesViewModel(client())
            model.setMeal(Meal.breakfast)
            model.setVegetarian(true)
            model.toggleAllergen(Allergen.fish)
            model.toggleAllergen(Allergen.nuts)
            model.toggleAllergen(Allergen.nuts)
            model.find()
            advanceUntilIdle()

            assertEquals(RecipeStep.Offer, model.state.value.step)
            assertEquals(
                listOf("pancakes"),
                model.state.value.offer
                    ?.recipes
                    ?.map { it.id },
            )
            assertTrue(
                """POST /recipes/suggest  {"meal":"breakfast","allergens":["fish"],"vegetarian":true}""" in calls,
                calls.toString(),
            )
        }

    @Test
    fun aRecipeIsScaledAndBecomesAPlan() =
        runTest(dispatcher) {
            val model = RecipesViewModel(client())
            model.find()
            advanceUntilIdle()
            model.choose("pancakes")
            advanceUntilIdle()
            assertEquals(RecipeStep.Plan, model.state.value.step)
            assertEquals(
                150.0,
                model.state.value.detail
                    ?.lines
                    ?.first()
                    ?.amount,
            )
            assertEquals(
                listOf("lena"),
                model.state.value.friends
                    .map { it.id },
            )

            model.setServings(4)
            advanceUntilIdle()
            assertEquals(
                300.0,
                model.state.value.detail
                    ?.lines
                    ?.first()
                    ?.amount,
            )
            model.setServings(99)
            advanceUntilIdle()
            assertEquals(RecipesViewModel.MAX_SERVINGS, model.state.value.servings)

            var created: String? = null
            model.create { created = it.id }
            assertEquals(null, created)

            model.toggleAtHome("flour")
            model.pickFriend("lena")
            model.setShopper(RecipePlanInput.Shopper.friend)
            model.setServings(4)
            advanceUntilIdle()
            model.create { created = it.id }
            advanceUntilIdle()

            assertEquals("k1", created)
            assertTrue(
                """POST /recipes/pancakes/plan """ +
                    """ {"friend_id":"lena","shopper":"friend","servings":4,"at_home":["flour"]}""" in
                    calls,
                calls.toString(),
            )
        }

    @Test
    fun goingBackKeepsTheFilters() =
        runTest(dispatcher) {
            val model = RecipesViewModel(client())
            model.setMeal(Meal.dinner)
            model.find()
            advanceUntilIdle()
            model.choose("pancakes")
            advanceUntilIdle()

            model.back()
            assertEquals(RecipeStep.Offer, model.state.value.step)
            model.back()
            assertEquals(RecipeStep.Filters, model.state.value.step)
            assertEquals(Meal.dinner, model.state.value.meal)
        }

    @Test
    fun aRecipeFromTheAssistantGoesBackToTheFilters() =
        runTest(dispatcher) {
            val model = RecipesViewModel(client())
            model.choose("pancakes")
            advanceUntilIdle()
            assertEquals(RecipeStep.Plan, model.state.value.step)

            model.back()
            assertEquals(RecipeStep.Filters, model.state.value.step)
        }
}
