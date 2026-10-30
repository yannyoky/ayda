package app.ayda.android.ui.chat

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PressButton
import app.ayda.android.ui.QuietButton
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.Russian
import app.ayda.android.ui.social.Avatar
import app.ayda.api.models.Attachment
import app.ayda.api.models.ChatUploadInput
import app.ayda.api.models.ConversationKind
import app.ayda.api.models.Message
import app.ayda.shared.chat.ChatViewModel
import app.ayda.shared.chat.PendingMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
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
    // Circle recording covers the whole chat, in the same window so the held finger keeps recording.
    var overlay by remember { mutableStateOf<(@Composable () -> Unit)?>(null) }
    Box(Modifier.fillMaxSize()) {
        ChatContent(model, meId, onBack, onMeetup, onOverlay = { overlay = it })
        overlay?.invoke()
    }
}

@Composable
private fun ChatContent(
    model: ChatViewModel,
    meId: String,
    onBack: () -> Unit,
    onMeetup: () -> Unit,
    onOverlay: ((@Composable () -> Unit)?) -> Unit,
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
                    // The meetup is the chat's main action: a round accent spark, so a long title keeps its room
                    PressButton(
                        onClick = onMeetup,
                        containerColor = colors.accent,
                        contentColor = colors.onAccent,
                        shape = CircleShape,
                        contentPadding = PaddingValues(0.dp),
                        modifier = Modifier.size(44.dp),
                    ) {
                        AydaIcon(
                            R.drawable.ic_spark,
                            colors.onAccent,
                            contentDescription = stringResource(R.string.meetup_button),
                        )
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
            chat.canSend -> Composer(model, onOverlay)
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
                canEdit = mine && message.attachment == null && model.canEdit(message),
                onExpired = model::refresh,
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
    onExpired: () -> Unit,
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
        val circle = message.attachment?.takeIf { it.kind == Attachment.Kind.video_note }
        if (circle != null) {
            Row(
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (mine) {
                    Text(
                        message.time(),
                        style = small(),
                        color = colors.muted,
                        modifier = Modifier.clickable(role = Role.Button, onClick = onSelect),
                    )
                }
                VideoNoteContent(circle, onExpired)
                if (!mine) Text(message.time(), style = small(), color = colors.muted)
            }
        } else {
            Row(
                Modifier
                    .widthIn(max = 300.dp)
                    .clip(shape)
                    .background(if (mine) colors.plate else colors.surface)
                    .then(if (mine) Modifier.clickable(role = Role.Button, onClick = onSelect) else Modifier)
                    .padding(14.dp, 8.dp),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) { BubbleBody(message, mine, onExpired) }
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
private fun RowScope.BubbleBody(
    message: Message,
    mine: Boolean,
    onExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val attachment = message.attachment
    if (attachment != null) {
        Box(Modifier.weight(1f, fill = false)) { VoiceBubbleContent(attachment, mine, onExpired) }
    } else {
        Text(
            message.text,
            style = MaterialTheme.typography.bodyLarge,
            color = if (mine) colors.onPlate else colors.ink,
            modifier = Modifier.weight(1f, fill = false),
        )
    }
    val time =
        if (message.editedAt != null) {
            stringResource(R.string.chats_edited, message.time())
        } else {
            message.time()
        }
    Text(time, style = small(), color = if (mine) colors.onPlate.copy(alpha = 0.6f) else colors.muted)
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
    val text = message.text
    val kind = message.recording?.kind
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End) {
        if (kind == ChatUploadInput.Kind.video_note && !message.failed) {
            // A circle that is on its way: the round shape is there at once, with a spinner.
            PendingCircle()
        } else if (kind != null) {
            Row(
                modifier =
                    Modifier
                        .semantics { contentDescription = label }
                        .clip(RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp))
                        .then(
                            if (message.failed) {
                                Modifier.background(colors.surface).clickable(role = Role.Button, onClick = onRetry)
                            } else {
                                Modifier.background(colors.plate)
                            },
                        ).padding(14.dp, 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (message.failed) {
                    AydaIcon(R.drawable.ic_close, colors.ink, size = 18)
                } else {
                    CircularProgressIndicator(
                        color = colors.onPlate,
                        strokeWidth = 2.dp,
                        modifier = Modifier.size(18.dp),
                    )
                }
                Text(
                    label,
                    style = MaterialTheme.typography.labelLarge,
                    color = if (message.failed) colors.ink else colors.onPlate,
                )
            }
        } else {
            Text(
                text,
                style = MaterialTheme.typography.bodyLarge,
                color = if (message.failed) colors.ink else colors.onPlate,
                modifier =
                    Modifier
                        .widthIn(max = 300.dp)
                        .semantics { contentDescription = "$label: $text" }
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
        }
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
private fun Composer(
    model: ChatViewModel,
    onOverlay: ((@Composable () -> Unit)?) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val context = LocalContext.current
    val recorder = remember { VoiceRecorder(context) }
    val circles = remember { CircleRecorder(context) }
    var recording by remember { mutableStateOf(false) }
    // A circle is being recorded; null when not, else whether the sound is recorded too.
    var circleAudio by remember { mutableStateOf<Boolean?>(null) }
    var seconds by remember { mutableIntStateOf(0) }
    var micDenied by remember { mutableStateOf(false) }
    var cameraDenied by remember { mutableStateOf(false) }
    // The finger is dragged far enough to the left that releasing cancels the voice message.
    var willCancel by remember { mutableStateOf(false) }
    // What a hold on the button records; a tap switches it, like in Telegram.
    var circleMode by rememberSaveable { mutableStateOf(false) }
    // A short tooltip about the current mode, shown after a tap or a hold that was too short.
    var holdHint by remember { mutableStateOf(false) }
    LaunchedEffect(holdHint, circleMode) {
        if (holdHint) {
            delay(3000)
            holdHint = false
        }
    }
    DisposableEffect(Unit) { onDispose { recorder.cancel() } }

    fun startRecording() {
        micDenied = false
        cameraDenied = false
        recording = recorder.start()
        seconds = 0
    }

    fun startCircle(withAudio: Boolean) {
        micDenied = false
        cameraDenied = false
        seconds = 0
        circleAudio = withAudio
    }

    fun finishRecording() {
        if (circleAudio != null) {
            circles.stop()
            return
        }
        recording = false
        recorder.stop()?.let { model.sendRecording(ChatUploadInput.Kind.voice, it) }
    }

    fun cancelRecording() {
        if (circleAudio != null) {
            circles.cancel()
            circleAudio = null
            return
        }
        recording = false
        recorder.cancel()
    }
    val askMic =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) micDenied = true
        }
    val askCamera =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
            if (granted[Manifest.permission.CAMERA] == true) {
                startCircle(withAudio = granted[Manifest.permission.RECORD_AUDIO] == true)
            } else {
                cameraDenied = true
            }
        }
    val active = recording || circleAudio != null
    LaunchedEffect(active) {
        while (active) {
            delay(1000)
            seconds += 1
            if (recording && seconds >= MAX_VOICE_SECONDS) finishRecording()
        }
    }
    val circleActive = circleAudio != null
    DisposableEffect(circleActive) {
        if (circleActive) {
            onOverlay {
                CircleRecordingScreen(
                    recorder = circles,
                    withAudio = circleAudio ?: true,
                    seconds = seconds,
                    willCancel = willCancel,
                ) { bytes ->
                    circleAudio = null
                    bytes?.let { model.sendRecording(ChatUploadInput.Kind.video_note, it) }
                }
            }
        }
        onDispose { onOverlay(null) }
    }

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
    if (holdHint) {
        Text(
            stringResource(if (circleMode) R.string.chats_hint_circle else R.string.chats_hint_voice),
            style = small(),
            color = colors.muted,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
    if (micDenied || cameraDenied) {
        Text(
            stringResource(if (cameraDenied) R.string.chats_camera_denied else R.string.chats_mic_denied),
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
        if (recording) {
            RecordingBar(seconds, willCancel, Modifier.weight(1f))
        } else {
            OutlinedTextField(
                value = state.text,
                onValueChange = model::onTextChange,
                placeholder = { Text(stringResource(R.string.chats_placeholder)) },
                shape = MaterialTheme.shapes.medium,
                maxLines = 5,
                modifier = Modifier.weight(1f),
            )
        }
        if (active || (state.editing == null && state.text.isBlank())) {
            HoldRecordButton(
                circleMode = circleMode,
                recording = active,
                onTap = {
                    circleMode = !circleMode
                    holdHint = true
                },
                onPress = {
                    holdHint = false
                    val has = { permission: String ->
                        ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
                    }
                    if (circleMode) {
                        if (has(Manifest.permission.CAMERA) && has(Manifest.permission.RECORD_AUDIO)) {
                            startCircle(withAudio = true)
                            true
                        } else {
                            askCamera.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO))
                            false
                        }
                    } else if (has(Manifest.permission.RECORD_AUDIO)) {
                        startRecording()
                        recording
                    } else {
                        askMic.launch(Manifest.permission.RECORD_AUDIO)
                        false
                    }
                },
                onDrag = { willCancel = it },
                onRelease = { cancelled ->
                    willCancel = false
                    when {
                        cancelled -> cancelRecording()
                        seconds < 1 -> {
                            cancelRecording()
                            holdHint = true
                        }
                        else -> finishRecording()
                    }
                },
            )
        } else {
            ComposerButton(
                R.drawable.ic_arrow,
                stringResource(if (state.editing != null) R.string.chats_save else R.string.chats_send),
                enabled = state.canSend,
                onClick = model::send,
            )
        }
    }
}

@Composable
private fun ComposerButton(
    icon: Int,
    label: String,
    enabled: Boolean = true,
    accent: Boolean = true,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier =
            Modifier
                .size(52.dp)
                .clip(MaterialTheme.shapes.medium)
                .background(if (accent) colors.accent else colors.surface)
                .alpha(if (enabled) 1f else 0.4f),
    ) {
        AydaIcon(icon, if (accent) colors.onAccent else colors.ink, size = 20, contentDescription = label)
    }
}

/** The bar that replaces the text field while a voice message is being recorded. */
@Composable
private fun RecordingBar(
    seconds: Int,
    willCancel: Boolean,
    modifier: Modifier = Modifier,
) {
    val colors = LocalAydaColors.current
    Row(
        modifier
            .clip(MaterialTheme.shapes.medium)
            .background(colors.surface)
            .padding(16.dp, 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(Color(0xFFE5484D)))
        Text(formatSeconds(seconds), style = MaterialTheme.typography.titleMedium)
        Text(
            stringResource(if (willCancel) R.string.chats_release_cancel else R.string.chats_slide_cancel),
            style = small(),
            color = if (willCancel) colors.accent else colors.muted,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
    }
}

/**
 * Telegram-style record button: a tap switches between voice and circle mode, a hold records in the
 * current mode, release sends, sliding left cancels. [onPress] starts the recording and says whether
 * it started; [onDrag] reports whether releasing now would cancel.
 */
@Composable
private fun HoldRecordButton(
    circleMode: Boolean,
    recording: Boolean,
    onTap: () -> Unit,
    onPress: () -> Boolean,
    onDrag: (Boolean) -> Unit,
    onRelease: (cancelled: Boolean) -> Unit,
) {
    val colors = LocalAydaColors.current
    val tap by rememberUpdatedState(onTap)
    val press by rememberUpdatedState(onPress)
    val drag by rememberUpdatedState(onDrag)
    val release by rememberUpdatedState(onRelease)
    val label = stringResource(if (circleMode) R.string.chats_mode_circle else R.string.chats_mode_voice)
    Box(
        Modifier
            .size(if (recording) 64.dp else 52.dp)
            .clip(if (recording) CircleShape else MaterialTheme.shapes.medium)
            .background(colors.accent)
            .semantics { contentDescription = label }
            .pointerInput(Unit) {
                val cancelDistance = 80.dp.toPx()
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    val up = withTimeoutOrNull(viewConfiguration.longPressTimeoutMillis) { waitForUpOrCancellation() }
                    if (up != null) {
                        tap()
                        return@awaitEachGesture
                    }
                    if (!press()) {
                        waitForUpOrCancellation()
                        return@awaitEachGesture
                    }
                    var cancelled = false
                    while (true) {
                        val change = awaitPointerEvent().changes.first()
                        cancelled = change.position.x - down.position.x < -cancelDistance
                        drag(cancelled)
                        if (!change.pressed) break
                    }
                    release(cancelled)
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        AydaIcon(if (circleMode) R.drawable.ic_video_note else R.drawable.ic_mic, colors.onAccent, size = 22)
    }
}
