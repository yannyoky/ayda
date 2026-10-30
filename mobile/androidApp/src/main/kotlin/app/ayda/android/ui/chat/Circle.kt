package app.ayda.android.ui.chat

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.SurfaceTexture
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.view.Surface
import android.view.TextureView
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.day.AydaIcon
import app.ayda.api.models.Attachment
import kotlinx.coroutines.delay
import java.io.File

/** The server keeps at most 60 seconds of a circle (ADR 0019). */
const val MAX_CIRCLE_SECONDS = 60

/**
 * Records a circle from the front camera at SD quality into the app's cache. The file is read
 * and deleted as soon as recording ends, so a recording never stays on the phone; the server
 * crops it to a square and re-encodes it.
 */
class CircleRecorder(
    private val context: Context,
) {
    val capture: VideoCapture<Recorder> =
        VideoCapture.withOutput(
            Recorder
                .Builder()
                .setQualitySelector(
                    QualitySelector.from(Quality.SD, FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)),
                ).build(),
        )
    private var recording: Recording? = null
    private var keep = true

    /** `onFinished` gets the MP4, or null when cancelled or failed. Audio needs RECORD_AUDIO. */
    @SuppressLint("MissingPermission")
    fun start(
        withAudio: Boolean,
        onFinished: (ByteArray?) -> Unit,
    ) {
        if (recording != null) return
        val target = File.createTempFile("circle-", ".mp4", context.cacheDir)
        val options =
            FileOutputOptions
                .Builder(target)
                .setDurationLimitMillis(MAX_CIRCLE_SECONDS * 1000L)
                .build()
        val pending = capture.output.prepareRecording(context, options)
        keep = true
        recording =
            (if (withAudio) pending.withAudioEnabled() else pending).start(
                ContextCompat.getMainExecutor(context),
            ) { event ->
                if (event is VideoRecordEvent.Finalize) {
                    recording = null
                    val ok = !event.hasError() || event.error == VideoRecordEvent.Finalize.ERROR_DURATION_LIMIT_REACHED
                    val bytes = if (ok && keep) runCatching { target.readBytes() }.getOrNull() else null
                    target.delete()
                    onFinished(bytes?.takeIf { it.isNotEmpty() })
                }
            }
    }

    fun stop() {
        recording?.stop()
    }

    fun cancel() {
        keep = false
        recording?.stop()
    }
}

/** The live front camera in a circle; recording starts once the camera is ready. */
@Composable
fun CircleCamera(
    recorder: CircleRecorder,
    withAudio: Boolean,
    size: Dp = 220.dp,
    onFinished: (ByteArray?) -> Unit,
) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val colors = LocalAydaColors.current
    val preview = remember { Preview.Builder().build() }
    DisposableEffect(owner) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()
            val camera =
                if (provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) {
                    CameraSelector.DEFAULT_FRONT_CAMERA
                } else {
                    CameraSelector.DEFAULT_BACK_CAMERA
                }
            val bound =
                runCatching {
                    provider.unbindAll()
                    provider.bindToLifecycle(owner, camera, preview, recorder.capture)
                }
            if (bound.isSuccess) recorder.start(withAudio, onFinished) else onFinished(null)
        }, ContextCompat.getMainExecutor(context))
        onDispose {
            recorder.cancel()
            runCatching { future.get().unbindAll() }
        }
    }
    Box(Modifier.fillMaxWidth().padding(bottom = 8.dp), contentAlignment = Alignment.Center) {
        AndroidView(
            factory = { ctx ->
                PreviewView(ctx).apply {
                    // A TextureView, so the picture can be clipped to a circle.
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    preview.surfaceProvider = surfaceProvider
                }
            },
            modifier = Modifier.size(size).clip(CircleShape).background(colors.surface),
        )
    }
}

/** A circle ("кружок") in a chat: loops silently, plays with sound on tap (see [CirclePlayer]). */
@Composable
fun VideoNoteContent(
    attachment: Attachment,
    onExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val url = attachment.url
    if (attachment.status != Attachment.Status.ready || url == null) {
        val text =
            when (attachment.status) {
                Attachment.Status.expired -> R.string.chats_circle_expired
                Attachment.Status.failed -> R.string.chats_circle_failed
                else -> null
            }
        if (text == null) {
            // Still being prepared: a round placeholder with a spinner, like Telegram.
            PendingCircle()
        } else {
            Box(
                Modifier
                    .size(200.dp)
                    .clip(CircleShape)
                    .background(colors.surface)
                    .padding(24.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    stringResource(text),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                    textAlign = TextAlign.Center,
                )
            }
        }
        return
    }
    CirclePlayer(url, attachment.durationMs, size = 200.dp, onExpired = onExpired)
}

/** A circle that is being sent or prepared: the round shape is there at once, with a spinner. */
@Composable
fun PendingCircle() {
    val colors = LocalAydaColors.current
    Box(
        Modifier.size(200.dp).clip(CircleShape).background(colors.surface),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(color = colors.accent, modifier = Modifier.size(36.dp))
    }
}

/**
 * A video that plays with sound on tap, clipped to [shape]. It is loaded right away so the first
 * frame shows instead of an empty box. The play link is short-lived: [onExpired] asks for a fresh
 * one when loading fails.
 */
@Composable
fun PlayableVideo(
    url: String,
    durationMs: Int?,
    shape: Shape,
    playLabel: String,
    onExpired: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalAydaColors.current
    val total = (durationMs ?: 0) / 1000f
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    var surface by remember { mutableStateOf<Surface?>(null) }
    var ready by remember(url) { mutableStateOf(false) }
    var failed by remember(url) { mutableStateOf(false) }
    var playing by remember(url) { mutableStateOf(false) }
    var position by remember(url) { mutableFloatStateOf(0f) }
    DisposableEffect(url, surface) {
        val target = surface
        if (target == null) return@DisposableEffect onDispose {}
        val created = MediaPlayer()
        created.setAudioAttributes(
            AudioAttributes
                .Builder()
                .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .build(),
        )
        created.setSurface(target)
        created.setOnPreparedListener {
            ready = true
            // A seek draws the first frame without starting playback.
            it.seekTo(0)
        }
        created.setOnCompletionListener {
            playing = false
            position = 0f
        }
        created.setOnErrorListener { _, _, _ ->
            playing = false
            ready = false
            failed = true
            true
        }
        try {
            created.setDataSource(url)
            created.prepareAsync()
            player = created
        } catch (e: Exception) {
            created.release()
            failed = true
        }
        onDispose {
            created.release()
            if (player === created) player = null
            ready = false
            playing = false
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
            // The play link is short-lived: ask for fresh messages.
            failed -> onExpired()
            current == null || !ready -> Unit
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

    val label = if (playing) stringResource(R.string.chats_circle_pause) else playLabel
    Box(
        modifier
            .clip(shape)
            .background(colors.surface)
            .clickable(role = Role.Button, onClickLabel = label, onClick = ::toggle),
        contentAlignment = Alignment.Center,
    ) {
        AndroidView(
            factory = { ctx ->
                TextureView(ctx).apply {
                    surfaceTextureListener =
                        object : TextureView.SurfaceTextureListener {
                            override fun onSurfaceTextureAvailable(
                                texture: SurfaceTexture,
                                width: Int,
                                height: Int,
                            ) {
                                surface = Surface(texture)
                            }

                            override fun onSurfaceTextureSizeChanged(
                                texture: SurfaceTexture,
                                width: Int,
                                height: Int,
                            ) = Unit

                            override fun onSurfaceTextureDestroyed(texture: SurfaceTexture): Boolean {
                                player?.setSurface(null)
                                surface?.release()
                                surface = null
                                return true
                            }

                            override fun onSurfaceTextureUpdated(texture: SurfaceTexture) = Unit
                        }
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        if (!playing) {
            Box(
                Modifier.size(48.dp).clip(CircleShape).background(colors.plate.copy(alpha = 0.7f)),
                contentAlignment = Alignment.Center,
            ) {
                AydaIcon(R.drawable.ic_play, colors.onPlate, size = 20, contentDescription = label)
            }
        }
        val left = if (playing) total - position else total
        Text(
            formatSeconds(left.toInt().coerceAtLeast(0)),
            style = small(),
            color = colors.onPlate,
            modifier =
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 12.dp)
                    .background(colors.plate.copy(alpha = 0.7f), RoundedCornerShape(50))
                    .padding(8.dp, 2.dp),
        )
    }
}

/**
 * Telegram-style circle recording: covers the whole chat, the round preview sits in the centre.
 * The finger is still on the record button, so there are no buttons here: release sends, a slide
 * to the left cancels.
 */
@Composable
fun CircleRecordingScreen(
    recorder: CircleRecorder,
    withAudio: Boolean,
    seconds: Int,
    willCancel: Boolean,
    onFinished: (ByteArray?) -> Unit,
) {
    val colors = LocalAydaColors.current
    Column(
        Modifier
            .fillMaxSize()
            .background(colors.bg)
            .safeDrawingPadding()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.weight(1f))
        CircleCamera(recorder, withAudio, size = 300.dp, onFinished = onFinished)
        Row(
            Modifier.padding(top = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(Color(0xFFE5484D)))
            Text(formatSeconds(seconds), style = MaterialTheme.typography.titleMedium, color = colors.ink)
        }
        Text(
            stringResource(if (willCancel) R.string.chats_release_cancel else R.string.chats_slide_cancel),
            style = MaterialTheme.typography.labelLarge,
            color = if (willCancel) colors.accent else colors.muted,
            modifier = Modifier.padding(top = 8.dp),
        )
        Spacer(Modifier.weight(1f))
        // Keeps the preview clear of the record button that the finger is holding.
        Spacer(Modifier.size(64.dp))
    }
}
