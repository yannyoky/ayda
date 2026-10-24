package app.ayda.android.ui.chat

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.QuietButton
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.Russian
import app.ayda.android.ui.social.Avatar
import app.ayda.api.models.ConversationKind
import app.ayda.api.models.Message
import app.ayda.shared.chat.ChatViewModel
import app.ayda.shared.chat.PendingMessage
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.time.Clock
import kotlin.time.Duration.Companion.days

private val clock = DateTimeFormatter.ofPattern("HH:mm")

private val COOP_CHAT_TTL = 30.days
private val dayFormat = DateTimeFormatter.ofPattern("d MMMM", Russian)

private fun Message.time(): String =
    clock.format(
        java.time.Instant
            .ofEpochMilli(createdAt.toEpochMilliseconds())
            .atZone(ZoneId.systemDefault()),
    )

/** US-17: one chat, newest at the bottom; own messages can be deleted for everyone. */
@Composable
fun ChatScreen(
    model: ChatViewModel,
    meId: String,
    onBack: () -> Unit,
    onMeetup: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val chat = state.conversation
    LaunchedEffect(state.hidden) { if (state.hidden) onBack() }

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
            if (chat != null) {
                Avatar(chat.avatar(), size = 40)
                Text(
                    chat.title,
                    style = MaterialTheme.typography.headlineSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (chat.canSend) {
                    // The meetup is the chat's main action, so it is an accent pill, not a quiet link.
                    Button(
                        onClick = onMeetup,
                        shape = RoundedCornerShape(50),
                        colors =
                            ButtonDefaults.buttonColors(
                                containerColor = colors.accent,
                                contentColor = colors.onAccent,
                            ),
                        contentPadding = PaddingValues(16.dp, 10.dp),
                    ) {
                        Text(stringResource(R.string.meetup_button), style = MaterialTheme.typography.labelLarge)
                    }
                }
                IconButton(
                    onClick = model::askHide,
                    modifier = Modifier.size(44.dp).clip(RoundedCornerShape(50)).background(colors.surface),
                ) {
                    AydaIcon(
                        R.drawable.ic_trash,
                        colors.ink,
                        size = 18,
                        contentDescription = stringResource(R.string.chats_hide),
                    )
                }
            }
        }
        chat?.deletesAt?.let { deletesAt ->
            // Shown once the quest is over: the chat is deleted 30 days after that.
            if (deletesAt - Clock.System.now() < COOP_CHAT_TTL) {
                val day =
                    dayFormat.format(
                        java.time.Instant
                            .ofEpochMilli(deletesAt.toEpochMilliseconds())
                            .atZone(ZoneId.systemDefault()),
                    )
                Text(
                    stringResource(R.string.chats_deletes_at, day),
                    style = small(),
                    color = colors.muted,
                    modifier =
                        Modifier
                            .padding(16.dp, 0.dp, 16.dp, 8.dp)
                            .fillMaxWidth()
                            .background(colors.surface, MaterialTheme.shapes.medium)
                            .padding(14.dp, 8.dp),
                )
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
                state.loaded && state.messages.isEmpty() && state.pending.isEmpty() ->
                    Text(
                        stringResource(R.string.chats_no_messages),
                        style = MaterialTheme.typography.labelLarge,
                        color = colors.muted,
                        modifier = Modifier.align(Alignment.Center),
                    )
                else -> Messages(model, meId, coop = chat?.kind == ConversationKind.coop)
            }
        }
        if (state.tooFast) {
            Text(
                stringResource(R.string.chats_too_many),
                style = small(),
                color = colors.muted,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
        when {
            chat == null -> {}
            chat.canSend -> Composer(model)
            else ->
                Text(
                    stringResource(R.string.chats_closed),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    modifier =
                        Modifier
                            .padding(16.dp)
                            .fillMaxWidth()
                            .background(colors.surface, MaterialTheme.shapes.large)
                            .padding(16.dp),
                )
        }
    }

    if (state.askingHide) {
        AlertDialog(
            onDismissRequest = model::cancelHide,
            text = { Text(stringResource(R.string.chats_hide_confirm)) },
            confirmButton = {
                TextButton(
                    onClick = model::confirmHide,
                ) { Text(stringResource(R.string.chats_hide_yes)) }
            },
            dismissButton = { TextButton(onClick = model::cancelHide) { Text(stringResource(R.string.cancel)) } },
        )
    }

    state.deleting?.let {
        AlertDialog(
            onDismissRequest = model::cancelDelete,
            text = { Text(stringResource(R.string.chats_delete_confirm)) },
            confirmButton = {
                TextButton(
                    onClick = model::confirmDelete,
                ) { Text(stringResource(R.string.chats_delete_yes)) }
            },
            dismissButton = { TextButton(onClick = model::cancelDelete) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

/**
 * Laid out bottom-up. A lazy list keeps the item it showed in place when one is added below, so
 * the list scrolls down itself for the user's own messages, and for others' while the user is
 * at the bottom (someone reading older messages is not pulled away).
 */
@Composable
private fun Messages(
    model: ChatViewModel,
    meId: String,
    coop: Boolean,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val list = rememberLazyListState()
    val newestPending = state.pending.lastOrNull()?.clientId
    val newest = state.messages.lastOrNull()
    LaunchedEffect(newestPending) { if (newestPending != null) list.animateScrollToItem(0) }
    LaunchedEffect(newest?.id) {
        if (newest != null && (newest.author.id == meId || list.firstVisibleItemIndex <= 1)) {
            list.animateScrollToItem(0)
        }
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        state = list,
        reverseLayout = true,
        contentPadding =
            androidx.compose.foundation.layout
                .PaddingValues(16.dp, 8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        items(state.pending.asReversed(), key = { "p-${it.clientId}" }) { Pending(it, onRetry = { model.retry(it) }) }
        items(state.messages.asReversed(), key = { it.id }) { message ->
            val mine = message.author.id == meId
            Bubble(
                message,
                mine = mine,
                showAuthor = coop && !mine,
                selected = state.selected == message.id,
                canEdit = mine && model.canEdit(message),
                onSelect = { model.select(message) },
                onEdit = { model.startEdit(message) },
                onDelete = { model.askDelete(message) },
            )
        }
        if (state.hasOlder) {
            item(key = "older") {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    QuietButton(stringResource(R.string.chats_older), onClick = model::loadOlder)
                }
            }
        }
    }
}

@Composable
private fun Bubble(
    message: Message,
    mine: Boolean,
    showAuthor: Boolean,
    selected: Boolean,
    canEdit: Boolean,
    onSelect: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val shape =
        if (mine) RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp) else RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)
    Column(Modifier.fillMaxWidth(), horizontalAlignment = if (mine) Alignment.End else Alignment.Start) {
        if (showAuthor) {
            Text(
                message.author.firstName,
                style = small(),
                color = colors.muted,
                modifier = Modifier.padding(horizontal = 12.dp),
            )
        }
        Row(
            Modifier
                .widthIn(max = 300.dp)
                .clip(shape)
                .background(if (mine) colors.plate else colors.surface)
                .then(if (mine) Modifier.clickable(role = Role.Button, onClick = onSelect) else Modifier)
                .padding(14.dp, 8.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                message.text,
                style = MaterialTheme.typography.bodyLarge,
                color = if (mine) colors.onPlate else colors.ink,
                modifier = Modifier.weight(1f, fill = false),
            )
            val time =
                if (message.editedAt != null) {
                    stringResource(R.string.chats_edited, message.time())
                } else {
                    message.time()
                }
            Text(time, style = small(), color = if (mine) colors.onPlate.copy(alpha = 0.6f) else colors.muted)
        }
        if (mine && selected) {
            Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (canEdit) {
                    MessageAction(stringResource(R.string.chats_edit), icon = null, onClick = onEdit)
                }
                MessageAction(stringResource(R.string.chats_delete), icon = R.drawable.ic_trash, onClick = onDelete)
            }
        }
    }
}

@Composable
private fun MessageAction(
    text: String,
    icon: Int?,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(
        Modifier
            .clip(MaterialTheme.shapes.medium)
            .background(colors.surface)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(12.dp, 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        icon?.let { AydaIcon(it, colors.ink, size = 16) }
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
private fun Pending(
    message: PendingMessage,
    onRetry: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val label = stringResource(if (message.failed) R.string.chats_failed else R.string.chats_sending)
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End) {
        Text(
            message.text,
            style = MaterialTheme.typography.bodyLarge,
            color = if (message.failed) colors.ink else colors.onPlate,
            modifier =
                Modifier
                    .widthIn(max = 300.dp)
                    .semantics { contentDescription = "$label: ${message.text}" }
                    .clip(RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp))
                    .then(
                        if (message.failed) {
                            Modifier
                                .background(colors.surface)
                                .border(
                                    BorderStroke(2.dp, colors.accent),
                                    RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp),
                                ).clickable(role = Role.Button, onClick = onRetry)
                        } else {
                            Modifier.background(colors.plate).alpha(0.6f)
                        },
                    ).padding(14.dp, 8.dp),
        )
        if (message.failed) {
            Text(
                label,
                style = small(),
                color = colors.muted,
                modifier = Modifier.padding(horizontal = 8.dp),
            )
        }
    }
}

@Composable
private fun Composer(model: ChatViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    if (state.editing != null) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                stringResource(R.string.chats_editing),
                style = small(),
                color = colors.muted,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = model::cancelEdit) { Text(stringResource(R.string.cancel)) }
        }
    }
    if (state.editTooLate) {
        Text(
            stringResource(R.string.chats_edit_too_late),
            style = small(),
            color = colors.muted,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
    Row(
        Modifier.fillMaxWidth().padding(16.dp, 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = state.text,
            onValueChange = model::onTextChange,
            placeholder = { Text(stringResource(R.string.chats_placeholder)) },
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
                contentDescription =
                    stringResource(if (state.editing != null) R.string.chats_save else R.string.chats_send),
            )
        }
    }
}
