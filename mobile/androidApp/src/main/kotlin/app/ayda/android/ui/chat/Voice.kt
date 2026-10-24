package app.ayda.android.ui.chat

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.day.AydaIcon
import app.ayda.api.models.Attachment
import kotlinx.coroutines.delay
import java.io.File

/** The server keeps at most 5 minutes of a voice message (ADR 0019). */
const val MAX_VOICE_SECONDS = 300

fun formatSeconds(total: Int): String = "%d:%02d".format(total / 60, total % 60)

/**
 * Records AAC in MP4 to the app's cache. The file is read and deleted as soon as recording ends,
 * so a recording never stays on the phone.
 */
class VoiceRecorder(
    private val context: Context,
) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null

    val recording: Boolean get() = recorder != null

    fun start(): Boolean {
        val target = File.createTempFile("voice-", ".m4a", context.cacheDir)
        val media =
            if (Build.VERSION.SDK_INT >=
                Build.VERSION_CODES.S
            ) {
                MediaRecorder(context)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }
        return try {
            media.setAudioSource(MediaRecorder.AudioSource.MIC)
            media.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            media.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            media.setAudioChannels(1)
            media.setAudioSamplingRate(44_100)
            media.setAudioEncodingBitRate(64_000)
            media.setOutputFile(target.absolutePath)
            media.prepare()
            media.start()
            recorder = media
            file = target
            true
        } catch (e: Exception) {
            media.release()
            target.delete()
            false
        }
    }

    /** The recording, or null when it is too short to keep or the recorder failed. */
    fun stop(): ByteArray? {
        val media = recorder ?: return null
        val target = file
        recorder = null
        file = null
        val ok = runCatching { media.stop() }.isSuccess
        media.release()
        val bytes = if (ok) target?.readBytes() else null
        target?.delete()
        return bytes?.takeIf { it.isNotEmpty() }
    }

    fun cancel() {
        stop()
    }
}

/** A voice message: play and pause, with the time left while playing. */
@Composable
fun VoiceBubbleContent(
    attachment: Attachment,
    mine: Boolean,
    onExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val muted = if (mine) colors.onPlate.copy(alpha = 0.6f) else colors.muted
    val tint = if (mine) colors.onPlate else colors.ink
    val url = attachment.url
    if (attachment.status != Attachment.Status.ready || url == null) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AydaIcon(R.drawable.ic_mic, muted, size = 18)
            Text(
                stringResource(
                    if (attachment.status ==
                        Attachment.Status.failed
                    ) {
                        R.string.chats_voice_failed
                    } else {
                        R.string.chats_voice_processing
                    },
                ),
                style = MaterialTheme.typography.labelLarge,
                color = muted,
            )
        }
        return
    }
    val total = (attachment.durationMs ?: 0) / 1000f
    var player by remember(url) { mutableStateOf<MediaPlayer?>(null) }
    var playing by remember(url) { mutableStateOf(false) }
    var position by remember(url) { mutableFloatStateOf(0f) }
    DisposableEffect(url) {
        onDispose {
            player?.release()
            player = null
        }
    }
    LaunchedEffect(playing) {
        while (playing) {
            position = (player?.currentPosition ?: 0) / 1000f
            delay(200)
        }
    }

    fun toggle() {
        val current = player
        when {
            current == null -> {
                val created = MediaPlayer()
                created.setAudioAttributes(
                    AudioAttributes
                        .Builder()
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .build(),
                )
                created.setOnPreparedListener {
                    it.start()
                    playing = true
                }
                created.setOnCompletionListener {
                    playing = false
                    position = 0f
                }
                created.setOnErrorListener { _, _, _ ->
                    playing = false
                    player?.release()
                    player = null
                    // The play link is short-lived: ask for fresh messages.
                    onExpired()
                    true
                }
                try {
                    created.setDataSource(url)
                    created.prepareAsync()
                    player = created
                } catch (e: Exception) {
                    created.release()
                    onExpired()
                }
            }
            current.isPlaying -> {
                current.pause()
                playing = false
            }
            else -> {
                current.start()
                playing = true
            }
        }
    }

    Row(
        Modifier.widthIn(min = 180.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        IconButton(
            onClick = ::toggle,
            modifier =
                Modifier
                    .size(36.dp)
                    .clip(RoundedCornerShape(50))
                    .background(if (mine) colors.onPlate.copy(alpha = 0.15f) else colors.bg),
        ) {
            AydaIcon(
                if (playing) R.drawable.ic_pause else R.drawable.ic_play,
                tint,
                size = 16,
                contentDescription =
                    stringResource(
                        if (playing) R.string.chats_voice_pause else R.string.chats_voice_play,
                    ),
            )
        }
        val progress = if (total > 0f) (position / total).coerceIn(0f, 1f) else 0f
        Box(
            Modifier
                .weight(1f)
                .height(4.dp)
                .clip(RoundedCornerShape(50))
                .background(if (mine) colors.onPlate.copy(alpha = 0.2f) else colors.bg),
        ) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(progress).background(colors.accent))
        }
        val left = if (playing) total - position else total
        Text(formatSeconds(left.toInt().coerceAtLeast(0)), style = small(), color = muted)
    }
}
