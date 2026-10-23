package app.ayda.android.ui.assistant

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringArrayResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.chat.small
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.Russian
import app.ayda.android.ui.recipes.label
import app.ayda.api.models.AssistantCard
import app.ayda.api.models.AssistantEvent
import app.ayda.api.models.AssistantMessage
import app.ayda.api.models.AssistantPlace
import app.ayda.api.models.DayQuest
import app.ayda.api.models.QuestState
import app.ayda.api.models.RecipeCard
import app.ayda.shared.assistant.AssistantViewModel
import java.text.NumberFormat
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val bubbleMine = RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp)
private val bubbleTheirs = RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)

/**
 * The day chat with the assistant (ADR 0013). [quest] is the quest of this topic, or null for the
 * day topic that the check-in opens. Cards carry facts from code: places, recipes, a quest.
 */
@Composable
fun AssistantScreen(
    model: AssistantViewModel,
    quest: DayQuest?,
    /** The current state of today's quests, so a quest card knows whether it can still be taken. */
    questStates: Map<String, QuestState>,
    onBack: () -> Unit,
    onCook: (String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    Column(
        Modifier
            .fillMaxSize()
            .background(colors.bg)
            .safeDrawingPadding()
            .imePadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp, 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.size(44.dp).clip(RoundedCornerShape(50)).background(colors.surface),
            ) {
                AydaIcon(
                    R.drawable.ic_back,
                    colors.ink,
                    size = 20,
                    contentDescription = stringResource(R.string.chats_back),
                )
            }
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.assistant_title), style = MaterialTheme.typography.headlineSmall)
                if (quest != null) {
                    Text(
                        stringResource(R.string.assistant_about, quest.title),
                        style = small(),
                        color = colors.muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        state.error?.let { error ->
            Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(error, style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = model::refresh) { Text(stringResource(R.string.retry)) }
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when {
                !state.loaded && state.error == null ->
                    CircularProgressIndicator(color = colors.accent, modifier = Modifier.align(Alignment.Center))
                state.loaded && state.messages.isEmpty() && !state.typing ->
                    Text(
                        stringResource(if (quest != null) R.string.assistant_empty_quest else R.string.assistant_empty),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.muted,
                        modifier =
                            Modifier
                                .align(Alignment.BottomCenter)
                                .padding(16.dp)
                                .fillMaxWidth()
                                .background(colors.surface, MaterialTheme.shapes.large)
                                .padding(16.dp),
                    )
                else -> Messages(model, questStates, onCook)
            }
        }
        state.failed?.let {
            Row(
                Modifier
                    .padding(16.dp, 4.dp)
                    .fillMaxWidth()
                    .background(colors.surface, MaterialTheme.shapes.medium)
                    .padding(start = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    stringResource(R.string.assistant_failed),
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = model::retry) { Text(stringResource(R.string.retry)) }
            }
        }
        if (state.showHints) {
            val hints =
                stringArrayResource(
                    if (quest !=
                        null
                    ) {
                        R.array.assistant_hints_quest
                    } else {
                        R.array.assistant_hints
                    },
                )
            Row(
                Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                hints.forEach { hint ->
                    Button(
                        onClick = { model.ask(hint) },
                        shape = RoundedCornerShape(50),
                        colors =
                            ButtonDefaults.buttonColors(
                                containerColor = colors.surface,
                                contentColor = colors.ink,
                            ),
                        contentPadding = PaddingValues(14.dp, 0.dp),
                        modifier = Modifier.height(36.dp),
                    ) { Text(hint, style = MaterialTheme.typography.labelLarge) }
                }
            }
        }
        if (state.limitReached) {
            Text(
                stringResource(R.string.assistant_limit),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
                modifier =
                    Modifier
                        .padding(16.dp)
                        .fillMaxWidth()
                        .background(colors.surface, MaterialTheme.shapes.large)
                        .padding(16.dp),
            )
        } else if (state.loaded) {
            Composer(model)
        }
    }
}

/** Laid out bottom-up, so the newest message stays in view. */
@Composable
private fun Messages(
    model: AssistantViewModel,
    questStates: Map<String, QuestState>,
    onCook: (String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    LazyColumn(
        Modifier.fillMaxSize(),
        reverseLayout = true,
        contentPadding = PaddingValues(16.dp, 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (state.typing) {
            item(key = "typing") { Typing() }
            item(key = "waiting") { Bubble(state.waiting.orEmpty(), mine = true, faded = true) }
        }
        items(state.messages.asReversed(), key = { it.id }) { message ->
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Bubble(message.text, mine = message.role == AssistantMessage.Role.user)
                message.cards.forEach { card -> CardView(card, model, questStates, onCook) }
            }
        }
    }
}

@Composable
private fun Bubble(
    text: String,
    mine: Boolean,
    faded: Boolean = false,
) {
    val colors = LocalAydaColors.current
    Column(Modifier.fillMaxWidth(), horizontalAlignment = if (mine) Alignment.End else Alignment.Start) {
        Text(
            text,
            style = MaterialTheme.typography.bodyLarge,
            color = if (mine) colors.onPlate else colors.ink,
            modifier =
                Modifier
                    .widthIn(max = 300.dp)
                    .clip(if (mine) bubbleMine else bubbleTheirs)
                    .background(if (mine) colors.plate else colors.surface)
                    .alpha(if (faded) 0.6f else 1f)
                    .padding(14.dp, 8.dp),
        )
    }
}

@Composable
private fun Typing() {
    val colors = LocalAydaColors.current
    val label = stringResource(R.string.assistant_typing)
    Row(
        Modifier
            .semantics { liveRegion = LiveRegionMode.Polite }
            .clip(bubbleTheirs)
            .background(colors.surface)
            .padding(14.dp, 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CircularProgressIndicator(color = colors.accent, strokeWidth = 2.dp, modifier = Modifier.size(14.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, color = colors.muted)
    }
}

@Composable
private fun CardView(
    card: AssistantCard,
    model: AssistantViewModel,
    questStates: Map<String, QuestState>,
    onCook: (String) -> Unit,
) {
    val colors = LocalAydaColors.current
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        card.note?.let {
            Text(
                it,
                style = small(),
                color = colors.muted,
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .background(colors.surface, MaterialTheme.shapes.medium)
                        .padding(14.dp, 8.dp),
            )
        }
        card.places.forEach { PlaceView(it) }
        card.events.forEach { EventView(it) }
        card.recipes.forEach { RecipeView(it, onCook) }
        card.quest?.let { quest ->
            val current = questStates[quest.id] ?: quest.state
            QuestIdea(quest, canTake = model.canTake(quest.id, current), onTake = { model.take(quest.id) })
        }
        card.attribution?.let {
            Text(it, style = small(), color = colors.muted, modifier = Modifier.padding(horizontal = 4.dp))
        }
    }
}

@Composable
private fun PlaceView(place: AssistantPlace) {
    val colors = LocalAydaColors.current
    val uriHandler = LocalUriHandler.current
    val meta =
        listOfNotNull(
            stringResource(place.kind.label()),
            place.address,
            distance(place.distanceM),
            if (place.openNow == true) stringResource(R.string.assistant_open_now) else null,
        ).joinToString(" · ")
    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface, MaterialTheme.shapes.large)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(place.name, style = MaterialTheme.typography.titleMedium)
        Text(meta, style = small(), color = colors.muted)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MapLink(stringResource(R.string.assistant_on_2gis)) { runCatching { uriHandler.openUri(place.gisUrl) } }
            MapLink(
                stringResource(R.string.assistant_on_yandex),
            ) { runCatching { uriHandler.openUri(place.yandexUrl) } }
        }
    }
}

private val eventWhen = DateTimeFormatter.ofPattern("EEE, d MMMM, HH:mm", Russian)

@Composable
private fun EventView(event: AssistantEvent) {
    val colors = LocalAydaColors.current
    val uriHandler = LocalUriHandler.current
    val starts =
        java.time.Instant
            .ofEpochMilli(event.startsAt.toEpochMilliseconds())
            .atZone(ZoneId.systemDefault())
    val price =
        when {
            event.isFree -> stringResource(R.string.event_free)
            event.priceMin != null ->
                stringResource(R.string.event_from, NumberFormat.getIntegerInstance(Russian).format(event.priceMin))
            else -> null
        }
    val far =
        if (event.distanceKm < 1) {
            stringResource(R.string.assistant_event_here)
        } else {
            stringResource(R.string.assistant_event_far, event.distanceKm.toInt())
        }
    val meta = listOfNotNull(event.venue, event.city, far, price).joinToString(" · ")
    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface, MaterialTheme.shapes.large)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(event.title, style = MaterialTheme.typography.titleMedium)
        Text(eventWhen.format(starts), style = MaterialTheme.typography.bodyMedium)
        Text(meta, style = small(), color = colors.muted)
        MapLink(stringResource(R.string.assistant_event_open)) { runCatching { uriHandler.openUri(event.url) } }
    }
}

@Composable
private fun MapLink(
    text: String,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Button(
        onClick = onClick,
        shape = MaterialTheme.shapes.medium,
        colors = ButtonDefaults.buttonColors(containerColor = colors.bg, contentColor = colors.ink),
        contentPadding = PaddingValues(12.dp, 0.dp),
        modifier = Modifier.height(36.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
        AydaIcon(R.drawable.ic_external, colors.ink, size = 14, modifier = Modifier.padding(start = 4.dp))
    }
}

@Composable
private fun RecipeView(
    recipe: RecipeCard,
    onCook: (String) -> Unit,
) {
    val colors = LocalAydaColors.current
    val allergens =
        if (recipe.allergens.isEmpty()) {
            stringResource(R.string.recipes_no_allergens)
        } else {
            stringResource(R.string.recipes_contains, recipe.allergens.map { it.label() }.joinToString(", "))
        }
    val cook = stringResource(R.string.assistant_cook, recipe.title)
    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface, MaterialTheme.shapes.large)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(recipe.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text(stringResource(R.string.recipes_minutes, recipe.minutes), style = small(), color = colors.muted)
        }
        recipe.why?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        Text(allergens, style = small(), color = colors.muted)
        Button(
            onClick = { onCook(recipe.id) },
            shape = MaterialTheme.shapes.medium,
            colors = ButtonDefaults.buttonColors(containerColor = colors.plate, contentColor = colors.onPlate),
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = cook },
        ) { Text(stringResource(R.string.recipes_choose), style = MaterialTheme.typography.labelLarge) }
    }
}

@Composable
private fun QuestIdea(
    quest: DayQuest,
    canTake: Boolean,
    onTake: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val take = stringResource(R.string.assistant_take_quest, quest.title)
    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.surface, MaterialTheme.shapes.large)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(quest.title, style = MaterialTheme.typography.titleMedium)
        Text(
            stringResource(R.string.quest_minutes, quest.durationMin) + " · " +
                stringResource(R.string.quest_points, quest.basePoints),
            style = small(),
            color = colors.muted,
        )
        if (canTake) {
            Button(
                onClick = onTake,
                shape = MaterialTheme.shapes.medium,
                colors = ButtonDefaults.buttonColors(containerColor = colors.accent, contentColor = colors.onAccent),
                modifier = Modifier.fillMaxWidth().semantics { contentDescription = take },
            ) { Text(stringResource(R.string.assistant_take), style = MaterialTheme.typography.labelLarge) }
        } else {
            Text(stringResource(R.string.assistant_taken), style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun Composer(model: AssistantViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    Column(Modifier.fillMaxWidth().padding(16.dp, 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = state.text,
                onValueChange = model::onTextChange,
                placeholder = { Text(stringResource(R.string.assistant_placeholder)) },
                shape = MaterialTheme.shapes.medium,
                maxLines = 5,
                modifier = Modifier.weight(1f),
            )
            IconButton(
                onClick = model::send,
                enabled = state.canSend,
                modifier =
                    Modifier
                        .size(52.dp)
                        .clip(MaterialTheme.shapes.medium)
                        .background(colors.accent)
                        .alpha(if (state.canSend) 1f else 0.4f),
            ) {
                AydaIcon(
                    R.drawable.ic_arrow,
                    colors.onAccent,
                    size = 20,
                    contentDescription = stringResource(R.string.chats_send),
                )
            }
        }
        if (state.messagesLeft <= 10) {
            Text(stringResource(R.string.assistant_left, state.messagesLeft), style = small(), color = colors.muted)
        }
    }
}

@Composable
private fun distance(meters: Int): String =
    if (meters < 1000) {
        stringResource(R.string.assistant_distance_m, meters)
    } else {
        stringResource(R.string.assistant_distance_km, "%.1f".format(meters / 1000.0).replace('.', ','))
    }

private fun AssistantPlace.Kind.label(): Int =
    when (this) {
        AssistantPlace.Kind.restaurant -> R.string.assistant_kind_restaurant
        AssistantPlace.Kind.cafe -> R.string.assistant_kind_cafe
        AssistantPlace.Kind.bar -> R.string.assistant_kind_bar
        AssistantPlace.Kind.pub -> R.string.assistant_kind_pub
        AssistantPlace.Kind.fast_food -> R.string.assistant_kind_fast_food
        AssistantPlace.Kind.park -> R.string.assistant_kind_park
        AssistantPlace.Kind.garden -> R.string.assistant_kind_garden
        AssistantPlace.Kind.embankment -> R.string.assistant_kind_embankment
        AssistantPlace.Kind.viewpoint -> R.string.assistant_kind_viewpoint
        AssistantPlace.Kind.square -> R.string.assistant_kind_square
    }
