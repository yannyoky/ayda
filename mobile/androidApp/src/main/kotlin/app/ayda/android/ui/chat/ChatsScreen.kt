package app.ayda.android.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.social.Avatar
import app.ayda.android.ui.social.formatAgo
import app.ayda.api.models.Conversation
import app.ayda.api.models.UserSummary
import app.ayda.shared.chat.ChatsViewModel

/** The avatar of a chat: the friend's in a DM, the quest's first letter in a co-op. */
fun Conversation.avatar(): UserSummary = peer ?: UserSummary(id, title)

/** US-17: chats with friends, latest first, with unread counts; a row of friends to start one. */
@Composable
fun ChatsScreen(
    model: ChatsViewModel,
    meId: String,
    onOpen: (String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    LifecycleResumeEffect(model) {
        model.refresh()
        onPauseOrDispose {}
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(colors.bg)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.chats_title),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(horizontal = 4.dp),
        )
        if (state.friends.isNotEmpty()) {
            Card {
                Text(stringResource(R.string.chats_start_title), style = MaterialTheme.typography.titleMedium)
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    state.friends.forEach { friend ->
                        val label = stringResource(R.string.chats_write_to, friend.firstName)
                        Column(
                            Modifier
                                .width(64.dp)
                                .clickable(enabled = !state.opening, role = Role.Button, onClickLabel = label) {
                                    model.openDirect(friend.id) { onOpen(it.id) }
                                }.semantics(mergeDescendants = true) { contentDescription = label },
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Avatar(UserSummary(friend.id, friend.firstName, friend.avatarUrl), size = 48)
                            Text(
                                friend.firstName,
                                style = MaterialTheme.typography.labelLarge,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                textAlign = TextAlign.Center,
                            )
                        }
                    }
                }
            }
        }
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
        if (state.loaded && state.conversations.isEmpty()) {
            Card {
                Text(
                    stringResource(if (state.friends.isEmpty()) R.string.chats_no_friends else R.string.chats_empty),
                    style = MaterialTheme.typography.bodyLarge,
                    color = colors.muted,
                )
            }
        }
        if (state.conversations.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large)) {
                state.conversations.forEachIndexed { index, chat ->
                    if (index > 0) HorizontalDivider(color = colors.bg)
                    ChatRow(chat, meId, onClick = { onOpen(chat.id) })
                }
            }
        }
    }
}

@Composable
private fun ChatRow(
    chat: Conversation,
    meId: String,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val last = chat.lastMessage
    val preview =
        when {
            last == null -> stringResource(R.string.chats_no_messages)
            last.author.id == meId -> stringResource(R.string.chats_you, last.text)
            else -> last.text
        }
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Avatar(chat.avatar(), size = 44)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    chat.title,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(formatAgo(chat.updatedAt), style = small(), color = colors.muted)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    preview,
                    style =
                        MaterialTheme.typography.bodyMedium.let {
                            if (chat.unreadCount >
                                0
                            ) {
                                it.copy(fontWeight = FontWeight.Bold)
                            } else {
                                it
                            }
                        },
                    color = if (chat.unreadCount > 0) colors.ink else colors.muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (chat.unreadCount > 0) UnreadBadge(chat.unreadCount)
            }
        }
    }
}

@Composable
fun UnreadBadge(count: Int) {
    val colors = LocalAydaColors.current
    val label = stringResource(R.string.chats_unread, count)
    Box(
        Modifier
            .heightIn(min = 20.dp)
            .widthIn(min = 20.dp)
            .background(colors.accent, CircleShape)
            .padding(horizontal = 6.dp)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        Text(if (count > 99) "99+" else "$count", style = small(), color = colors.onAccent)
    }
}

/** 12 sp captions: times and counters. */
@Composable
fun small(): TextStyle = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp, lineHeight = 16.sp)
