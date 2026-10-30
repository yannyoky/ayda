package app.ayda.android.ui.chat

import android.content.Context
import android.graphics.SurfaceTexture
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.ConnectivityManager
import android.os.PowerManager
import android.view.Surface
import android.view.TextureView
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.day.AydaIcon
import kotlinx.coroutines.delay

/**
 * How a circle is shown, like in Telegram: [Preview] loops without sound (or shows the first frame
 * when autoplay is off), [Playing] plays once with sound and a progress ring, [Paused] keeps the ring.
 */
enum class CircleMode { Preview, Playing, Paused }

/** What a tap on a circle in [mode] leads to. */
fun CircleMode.afterTap(): CircleMode =
    when (this) {
        CircleMode.Preview -> CircleMode.Playing
        CircleMode.Playing -> CircleMode.Paused
        CircleMode.Paused -> CircleMode.Playing
    }

/** The share of the circle's edge the progress ring covers, 0..1. */
fun circleProgress(
    positionMs: Int,
    durationMs: Int,
): Float = if (durationMs <= 0) 0f else (positionMs.toFloat() / durationMs).coerceIn(0f, 1f)

/** Seconds left to show on a circle: the whole length in preview, what is left while playing. */
fun circleSecondsLeft(
    mode: CircleMode,
    positionMs: Int,
    durationMs: Int,
): Int {
    val left = if (mode == CircleMode.Preview) durationMs else durationMs - positionMs
    return (left.coerceAtLeast(0) + 999) / 1000
}

/**
 * Circles play without sound on their own unless the phone asks to save data or battery; then
 * they show the first frame until tapped.
 */
fun mutedAutoplayAllowed(context: Context): Boolean {
    val connectivity = context.getSystemService(ConnectivityManager::class.java)
    val dataSaver = connectivity?.restrictBackgroundStatus == ConnectivityManager.RESTRICT_BACKGROUND_STATUS_ENABLED
    val batterySaver = context.getSystemService(PowerManager::class.java)?.isPowerSaveMode == true
    return !dataSaver && !batterySaver
}

/** Only one circle plays with sound at a time: starting another one returns the first to preview. */
private object SoundingCircle {
    var current: SoundClaim? = null
}

private class SoundClaim {
    private var stop: () -> Unit = {}

    fun take(stopIt: () -> Unit) {
        stop = stopIt
        val previous = SoundingCircle.current
        if (previous !== this) {
            SoundingCircle.current = this
            previous?.stop?.invoke()
        }
    }

    fun release() {
        if (SoundingCircle.current === this) SoundingCircle.current = null
    }
}

/**
 * A circle ("кружок") that behaves like in Telegram: it loops without sound in the chat, a tap
 * plays it from the start with sound and a progress ring along the edge, another tap pauses.
 * When it ends it goes back to the silent loop. The play link is short-lived: [onExpired] asks for
 * a fresh one when loading fails.
 */
@Composable
fun CirclePlayer(
    url: String,
    durationMs: Int?,
    size: Dp,
    onExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val autoplay = remember { mutedAutoplayAllowed(context) }
    val claim = remember { SoundClaim() }
    var surface by remember { mutableStateOf<Surface?>(null) }
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    var ready by remember(url) { mutableStateOf(false) }
    var mode by remember(url) { mutableStateOf(CircleMode.Preview) }
    var position by remember(url) { mutableIntStateOf(0) }
    var length by remember(url) { mutableIntStateOf(durationMs ?: 0) }
    // Bumped to retry after a failed load; a broken file asks for a fresh link only once.
    var attempt by remember { mutableIntStateOf(0) }
    var failed by remember(url) { mutableStateOf(false) }
    var reported by remember { mutableStateOf(false) }

    fun toPreview(current: MediaPlayer) {
        claim.release()
        current.setVolume(0f, 0f)
        current.isLooping = true
        current.seekTo(0)
        if (autoplay) current.start() else if (current.isPlaying) current.pause()
        mode = CircleMode.Preview
        position = 0
    }

    DisposableEffect(url, surface, attempt) {
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
        created.setVolume(0f, 0f)
        created.isLooping = true
        created.setOnPreparedListener {
            ready = true
            failed = false
            reported = false
            if (it.duration > 0) length = it.duration
            // Without autoplay a seek still draws the first frame instead of an empty circle.
            if (autoplay && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) it.start() else it.seekTo(0)
        }
        created.setOnCompletionListener { toPreview(it) }
        created.setOnErrorListener { _, _, _ ->
            ready = false
            failed = true
            mode = CircleMode.Preview
            claim.release()
            if (!reported) {
                reported = true
                onExpired()
            }
            true
        }
        try {
            created.setDataSource(url)
            created.prepareAsync()
            player = created
        } catch (e: Exception) {
            created.release()
            failed = true
            if (!reported) {
                reported = true
                onExpired()
            }
        }
        onDispose {
            claim.release()
            created.release()
            if (player === created) player = null
            ready = false
        }
    }

    // Stop with the app: nothing plays in the background, the silent loop resumes on return.
    DisposableEffect(owner) {
        val observer =
            LifecycleEventObserver { _, event ->
                val current = player
                if (current == null || !ready) return@LifecycleEventObserver
                when (event) {
                    Lifecycle.Event.ON_STOP ->
                        if (current.isPlaying) {
                            current.pause()
                            if (mode == CircleMode.Playing) mode = CircleMode.Paused
                        }
                    Lifecycle.Event.ON_START -> if (mode == CircleMode.Preview && autoplay) current.start()
                    else -> Unit
                }
            }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(mode, player) {
        while (mode == CircleMode.Playing) {
            position = player?.currentPosition ?: position
            delay(50)
        }
    }

    fun toggle() {
        val current = player
        if (current == null || !ready) {
            if (failed) {
                reported = true
                attempt++
                onExpired()
            }
            return
        }
        when (mode) {
            CircleMode.Preview -> {
                claim.take { player?.let(::toPreview) }
                current.isLooping = false
                current.setVolume(1f, 1f)
                current.seekTo(0)
                current.start()
                position = 0
            }
            CircleMode.Playing -> current.pause()
            CircleMode.Paused -> {
                claim.take { player?.let(::toPreview) }
                current.start()
            }
        }
        mode = mode.afterTap()
    }

    val active = mode != CircleMode.Preview
    // Like Telegram, a circle that is being watched grows a little.
    val shown by animateDpAsState(if (active) size * 1.2f else size, label = "circle size")
    val label =
        stringResource(if (mode == CircleMode.Playing) R.string.chats_circle_pause else R.string.chats_circle_play)
    val ringColor = colors.accent
    Box(
        Modifier
            .size(shown)
            .clip(CircleShape)
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
        if (active) {
            val progress = circleProgress(position, length)
            Canvas(Modifier.fillMaxSize()) {
                val stroke = 4.dp.toPx()
                drawArc(
                    color = ringColor,
                    startAngle = -90f,
                    sweepAngle = 360f * progress,
                    useCenter = false,
                    topLeft =
                        androidx.compose.ui.geometry
                            .Offset(stroke / 2, stroke / 2),
                    size =
                        androidx.compose.ui.geometry
                            .Size(this.size.width - stroke, this.size.height - stroke),
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
            }
        }
        if (mode == CircleMode.Paused || (mode == CircleMode.Preview && (!autoplay || failed))) {
            Box(
                Modifier.size(48.dp).clip(CircleShape).background(colors.plate.copy(alpha = 0.7f)),
                contentAlignment = Alignment.Center,
            ) {
                AydaIcon(R.drawable.ic_play, colors.onPlate, size = 20, contentDescription = label)
            }
        }
        Row(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 12.dp)
                .background(colors.plate.copy(alpha = 0.7f), RoundedCornerShape(50))
                .padding(8.dp, 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                formatSeconds(circleSecondsLeft(mode, position, length)),
                style = small(),
                color = colors.onPlate,
            )
            if (mode == CircleMode.Preview) AydaIcon(R.drawable.ic_muted, colors.onPlate, size = 12)
        }
    }
}
