package app.ayda.android.ui.social

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.Russian
import app.ayda.android.ui.day.StatsRow
import app.ayda.api.apis.SocialApi.WeekGetLadder
import app.ayda.api.models.Day
import app.ayda.api.models.Friend
import app.ayda.api.models.LadderEntry
import app.ayda.api.models.UserSummary
import app.ayda.shared.social.FriendsViewModel
import java.text.NumberFormat
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val dayMonth = DateTimeFormatter.ofPattern("d MMMM", Russian)

/** US-16 and US-12: the weekly ladder among friends, then the friends list with an invite. */
@Composable
fun FriendsScreen(
    model: FriendsViewModel,
    /** Today's streak and points, moved here from the Today screen. */
    day: Day?,
    onWrite: (Friend) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val context = LocalContext.current
    val inviteText = stringResource(R.string.friends_invite_text)
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
        Column(Modifier.padding(horizontal = 4.dp)) {
            state.ladder?.let {
                val start = java.time.LocalDate.parse(it.weekStart.toString())
                Text(
                    stringResource(R.string.friends_week_from, dayMonth.format(start)),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            }
            Text(stringResource(R.string.friends_title), style = MaterialTheme.typography.headlineLarge)
        }
        day?.let { StatsRow(it) }
        WeekSwitch(state.week, model::selectWeek)
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
        val ladder = state.ladder
        when {
            ladder == null -> {}
            state.alone ->
                Card {
                    Text(
                        stringResource(R.string.friends_alone),
                        style = MaterialTheme.typography.bodyLarge,
                        color = colors.muted,
                    )
                }
            else -> LadderView(ladder.propertyEntries)
        }
        FriendsList(
            friends = state.friends,
            inviting = state.inviting,
            inviteShared = state.inviteShared,
            onInvite = {
                model.invite { invite ->
                    val send =
                        Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, "$inviteText\n${invite.url}")
                    context.startActivity(Intent.createChooser(send, null))
                }
            },
            onRemove = model::askRemove,
            onWrite = onWrite,
        )
    }

    state.removing?.let { friend ->
        AlertDialog(
            onDismissRequest = model::cancelRemove,
            text = { Text(stringResource(R.string.friends_remove_confirm, friend.firstName)) },
            confirmButton = {
                TextButton(
                    onClick = model::confirmRemove,
                ) { Text(stringResource(R.string.friends_remove_yes)) }
            },
            dismissButton = { TextButton(onClick = model::cancelRemove) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun WeekSwitch(
    week: WeekGetLadder,
    onSelect: (WeekGetLadder) -> Unit,
) {
    val colors = LocalAydaColors.current
    val weeks =
        listOf(
            WeekGetLadder.current to R.string.friends_week_current,
            WeekGetLadder.previous to R.string.friends_week_previous,
        )
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        weeks.forEachIndexed { index, (value, label) ->
            SegmentedButton(
                selected = week == value,
                onClick = { onSelect(value) },
                shape = SegmentedButtonDefaults.itemShape(index, weeks.size),
                icon = {},
                colors =
                    SegmentedButtonDefaults.colors(
                        activeContainerColor = colors.plate,
                        activeContentColor = colors.onPlate,
                        inactiveContainerColor = colors.surface,
                        inactiveContentColor = colors.muted,
                        activeBorderColor = Color.Transparent,
                        inactiveBorderColor = Color.Transparent,
                    ),
            ) { Text(stringResource(label)) }
        }
    }
}

private fun points(n: Int): String = NumberFormat.getIntegerInstance(Russian).format(n)

@Composable
private fun LadderEntry.name(): String = if (isMe) stringResource(R.string.feed_me) else user.firstName

/** A podium for the top three (1st in the middle and tallest), then a list. */
@Composable
private fun LadderView(entries: List<LadderEntry>) {
    val colors = LocalAydaColors.current
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
        entries.getOrNull(1)?.let { Podium(it, 150.dp, leader = false) } ?: Spacer(Modifier.weight(1f))
        Podium(entries[0], 186.dp, leader = true)
        entries.getOrNull(2)?.let { Podium(it, 128.dp, leader = false) } ?: Spacer(Modifier.weight(1f))
    }
    val rest = entries.drop(3)
    if (rest.isEmpty()) return
    Column(Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large).padding(16.dp, 6.dp)) {
        rest.forEachIndexed { index, entry ->
            if (index > 0) HorizontalDivider(color = colors.bg)
            val label = "${stringResource(R.string.friends_rank, entry.rank)}: ${entry.name()}, ${points(entry.points)}"
            Row(
                Modifier.fillMaxWidth().height(52.dp).semantics(mergeDescendants = true) { contentDescription = label },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    "${entry.rank}",
                    style = MaterialTheme.typography.titleMedium,
                    color = colors.muted,
                    modifier = Modifier.width(24.dp),
                )
                Text(
                    entry.name(),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    stringResource(R.string.friends_streak, entry.streakDays),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
                Text(
                    points(entry.points),
                    style = MaterialTheme.typography.titleMedium,
                    color = if (entry.isMe) colors.onAccent else colors.ink,
                    modifier =
                        if (entry.isMe) {
                            Modifier
                                .background(
                                    colors.accent,
                                    MaterialTheme.shapes.small,
                                ).padding(6.dp, 0.dp)
                        } else {
                            Modifier
                        },
                )
            }
        }
    }
}

@Composable
private fun RowScope.Podium(
    entry: LadderEntry,
    height: Dp,
    leader: Boolean,
) {
    val colors = LocalAydaColors.current
    val (background, content) =
        when {
            entry.isMe -> colors.accent to colors.onAccent
            leader -> colors.plate to colors.onPlate
            else -> colors.surface to colors.ink
        }
    val label = "${stringResource(R.string.friends_rank, entry.rank)}: ${entry.name()}, ${points(entry.points)}"
    Column(
        Modifier
            .weight(1f)
            .height(height)
            .background(background, RoundedCornerShape(24.dp))
            .padding(12.dp)
            .semantics(mergeDescendants = true) { contentDescription = label },
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${entry.rank}",
                style = MaterialTheme.typography.headlineSmall,
                color = if (leader && !entry.isMe) colors.accent else content,
                modifier = Modifier.weight(1f),
            )
            if (leader) AydaIcon(R.drawable.ic_crown, if (entry.isMe) content else colors.accent, size = 22)
        }
        Column {
            Text(
                entry.name(),
                style = MaterialTheme.typography.titleMedium,
                color = content,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(points(entry.points), style = MaterialTheme.typography.labelLarge, color = content.copy(alpha = 0.75f))
        }
    }
}

@Composable
private fun FriendsList(
    friends: List<Friend>,
    inviting: Boolean,
    inviteShared: Boolean,
    onInvite: () -> Unit,
    onRemove: (Friend) -> Unit,
    onWrite: (Friend) -> Unit,
) {
    val colors = LocalAydaColors.current
    Card {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(stringResource(R.string.friends_list_title), style = MaterialTheme.typography.titleMedium)
            if (friends.isNotEmpty()) {
                Text(
                    "${friends.size}",
                    style = MaterialTheme.typography.titleMedium,
                    color = colors.muted,
                )
            }
        }
        PrimaryButton(stringResource(R.string.friends_invite), onClick = onInvite, enabled = !inviting)
        if (inviteShared) {
            Text(
                stringResource(R.string.friends_invite_shared),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
            )
        }
        friends.forEachIndexed { index, friend ->
            if (index > 0) HorizontalDivider(color = colors.bg)
            val since =
                dayMonth.format(
                    java.time.Instant
                        .ofEpochMilli(friend.since.toEpochMilliseconds())
                        .atZone(ZoneId.systemDefault()),
                )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Avatar(UserSummary(friend.id, friend.firstName, friend.avatarUrl), size = 36)
                Column(Modifier.weight(1f)) {
                    Text(
                        friend.firstName,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        stringResource(R.string.friends_since, since),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.muted,
                    )
                }
                IconButton(onClick = { onWrite(friend) }) {
                    AydaIcon(
                        R.drawable.ic_chat,
                        colors.ink,
                        size = 18,
                        contentDescription = stringResource(R.string.chats_write_to, friend.firstName),
                    )
                }
                IconButton(onClick = { onRemove(friend) }) {
                    AydaIcon(
                        R.drawable.ic_close,
                        colors.muted,
                        size = 18,
                        contentDescription = stringResource(R.string.friends_remove, friend.firstName),
                    )
                }
            }
        }
    }
}
