package app.ayda.android.ui.day

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ContentResolver
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.media.PhotoCompressor
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.chat.CircleCamera
import app.ayda.android.ui.chat.CircleRecorder
import app.ayda.android.ui.chat.formatSeconds
import app.ayda.api.models.Completion
import app.ayda.api.models.CreateUploadRequest
import app.ayda.api.models.Visibility
import app.ayda.shared.day.CompleteState
import app.ayda.shared.day.CompleteViewModel
import app.ayda.shared.day.PhotoError
import app.ayda.shared.day.PickedClip
import app.ayda.shared.day.PickedPhoto
import app.ayda.shared.media.MAX_VIDEO_BYTES
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.InputStream

/**
 * US-09/US-10: mark a taken quest done, choose who sees it, attach 1-3 photos, a video or a
 * circle for friends.
 */
@Composable
fun CompleteScreen(
    model: CompleteViewModel,
    onClose: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val result = state.result
    Column(
        Modifier
            .fillMaxSize()
            .background(colors.bg)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (result != null) {
            Success(result, onClose)
            return@Column
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            CategoryTile(state.quest.category, background = colors.plate, tint = colors.onPlate)
            Column(Modifier.weight(1f)) {
                Text(
                    stringResource(R.string.complete_title),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
                Text(state.quest.title, style = MaterialTheme.typography.headlineSmall)
            }
            IconButton(onClick = onClose, modifier = Modifier.size(44.dp).background(colors.surface, CircleShape)) {
                AydaIcon(R.drawable.ic_close, colors.ink, contentDescription = stringResource(R.string.close))
            }
        }
        Text(
            stringResource(R.string.complete_who),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(start = 4.dp, top = 4.dp),
        )
        listOf(Visibility.friends, Visibility.personal).forEach { visibility ->
            VisibilityOption(
                visibility,
                selected = state.visibility == visibility,
                points = model.expectedPoints(visibility),
                onSelect = { model.onVisibilityChange(visibility) },
            )
        }
        if (state.inFeed) PhotoSection(state, model)
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
        val upload = state.uploading
        PrimaryButton(
            if (upload != null && state.clip != null) {
                stringResource(R.string.complete_uploading_video)
            } else if (upload != null) {
                stringResource(R.string.complete_uploading, upload.current, upload.total)
            } else {
                stringResource(R.string.complete_submit)
            },
            onClick = model::submit,
            enabled = state.ready,
        )
    }
}

@Composable
private fun VisibilityOption(
    visibility: Visibility,
    selected: Boolean,
    points: Int,
    onSelect: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val (title, text) =
        when (visibility) {
            // `routine` is no longer offered; it stays in the contract for older quests.
            Visibility.friends, Visibility.routine -> R.string.complete_friends to R.string.complete_friends_text
            Visibility.personal -> R.string.complete_personal to R.string.complete_personal_text
        }
    val ink = if (selected) colors.onPlate else colors.ink
    val muted = ink.copy(alpha = 0.7f)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(if (selected) colors.plate else colors.surface)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onSelect)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(stringResource(title), style = MaterialTheme.typography.titleMedium, color = ink)
            Text(stringResource(text), style = MaterialTheme.typography.bodyMedium, color = muted)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                stringResource(R.string.complete_expected, points),
                style = MaterialTheme.typography.titleMedium,
                color = ink,
            )
            Text(
                stringResource(R.string.complete_multiplier, decimal(CompleteViewModel.multiplier(visibility))),
                style = MaterialTheme.typography.bodyMedium,
                color = muted,
            )
        }
    }
}

/** "1", "0,75", "1,1": multipliers the Russian way. */
private fun decimal(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else value.toString().trimEnd('0').replace('.', ',')

@Composable
private fun PhotoSection(
    state: CompleteState,
    model: CompleteViewModel,
) {
    val colors = LocalAydaColors.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var shot by rememberSaveable { mutableStateOf<String?>(null) }

    fun add(
        uri: Uri,
        temporary: Boolean,
    ) = scope.launch {
        val jpeg =
            withContext(Dispatchers.IO) {
                PhotoCompressor.compress(context.contentResolver, uri).also {
                    if (temporary) runCatching { context.contentResolver.delete(uri, null, null) }
                }
            }
        if (jpeg != null) model.addPhoto(jpeg) else model.photoFailed()
    }

    val gallery =
        rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            if (uri != null) add(uri, temporary = false)
        }
    val camera =
        rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
            val uri = shot?.let(Uri::parse)
            shot = null
            if (uri != null) {
                if (saved) {
                    add(
                        uri,
                        temporary = true,
                    )
                } else {
                    runCatching { context.contentResolver.delete(uri, null, null) }
                }
            }
        }

    fun shoot() {
        val dir = File(context.cacheDir, "camera").apply { mkdirs() }
        val file = File(dir, "shot-${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.photos", file)
        shot = uri.toString()
        try {
            camera.launch(uri)
        } catch (_: ActivityNotFoundException) {
            shot = null
            model.photoFailed()
        } catch (_: SecurityException) {
            shot = null
            model.photoFailed()
        }
    }

    // The app declares CAMERA for chat circles, so the camera app may only be opened once the
    // permission is granted.
    val askCamera =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) shoot() else model.photoFailed()
        }

    val videos =
        rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            if (uri == null) return@rememberLauncherForActivityResult
            scope.launch {
                val mime = context.contentResolver.getType(uri)
                val bytes = withContext(Dispatchers.IO) { readVideo(context.contentResolver, uri) }
                if (bytes != null) model.addVideo(bytes, mime) else model.photoFailed()
            }
        }

    // A circle is being recorded; null when not, else whether the sound is recorded too.
    val circles = remember { CircleRecorder(context) }
    var circleAudio by remember { mutableStateOf<Boolean?>(null) }
    var seconds by remember { mutableIntStateOf(0) }
    LaunchedEffect(circleAudio) {
        seconds = 0
        while (circleAudio != null) {
            delay(1000)
            seconds += 1
        }
    }
    val askCircle =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
            if (granted[Manifest.permission.CAMERA] == true) {
                circleAudio = granted[Manifest.permission.RECORD_AUDIO] == true
            } else {
                model.photoFailed()
            }
        }

    fun startCircle() {
        val camera = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
        val mic = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
        if (camera == PackageManager.PERMISSION_GRANTED && mic == PackageManager.PERMISSION_GRANTED) {
            circleAudio = true
        } else {
            askCircle.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO))
        }
    }

    Column(
        Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (state.photos.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                state.photos.forEachIndexed { index, photo -> Thumbnail(photo, index, model) }
                repeat(CompleteViewModel.MAX_PHOTOS - state.photos.size) { Box(Modifier.weight(1f)) }
            }
        }
        circleAudio?.let { withAudio ->
            CircleCamera(circles, withAudio) { bytes ->
                circleAudio = null
                bytes?.let(model::addCircle)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                IconButton(
                    onClick = {
                        circles.cancel()
                        circleAudio = null
                    },
                    modifier = Modifier.size(48.dp).background(colors.bg, CircleShape),
                ) {
                    AydaIcon(
                        R.drawable.ic_close,
                        colors.ink,
                        contentDescription = stringResource(R.string.chats_cancel_recording),
                    )
                }
                Text(
                    stringResource(R.string.chats_recording, formatSeconds(seconds)),
                    style = MaterialTheme.typography.titleMedium,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = { circles.stop() },
                    modifier = Modifier.size(48.dp).background(colors.accent, CircleShape),
                ) {
                    AydaIcon(
                        R.drawable.ic_check,
                        colors.onAccent,
                        contentDescription = stringResource(R.string.complete_circle_done),
                    )
                }
            }
        }
        state.clip?.let { clip -> ClipRow(clip, model::removeClip) }
        if (state.canAddPhoto && circleAudio == null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PhotoButton(stringResource(R.string.complete_gallery)) {
                    gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }
                PhotoButton(stringResource(R.string.complete_camera)) {
                    val granted =
                        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                            PackageManager.PERMISSION_GRANTED
                    if (granted) shoot() else askCamera.launch(Manifest.permission.CAMERA)
                }
            }
        }
        if (state.canAddClip && circleAudio == null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PhotoButton(stringResource(R.string.complete_video), R.drawable.ic_play) {
                    videos.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly))
                }
                PhotoButton(stringResource(R.string.complete_circle)) { startCircle() }
            }
        }
        Text(
            when (state.photoError) {
                PhotoError.TooBig -> stringResource(R.string.complete_photo_too_big)
                PhotoError.Unreadable -> stringResource(R.string.complete_photo_unreadable)
                PhotoError.VideoTooBig -> stringResource(R.string.complete_video_too_big)
                PhotoError.VideoUnsupported -> stringResource(R.string.complete_video_unsupported)
                null ->
                    stringResource(
                        if (state.clip != null) R.string.complete_video_hint else R.string.complete_photos_hint,
                    )
            },
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
        OutlinedTextField(
            value = state.caption,
            onValueChange = model::onCaptionChange,
            label = { Text(stringResource(R.string.complete_caption)) },
            placeholder = { Text(stringResource(R.string.complete_caption_placeholder)) },
            minLines = 2,
            shape = MaterialTheme.shapes.medium,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.Thumbnail(
    photo: PickedPhoto,
    index: Int,
    model: CompleteViewModel,
) {
    val colors = LocalAydaColors.current
    val image = remember(photo.id) { BitmapFactory.decodeByteArray(photo.jpeg, 0, photo.jpeg.size)?.asImageBitmap() }
    Box(
        Modifier
            .weight(1f)
            .aspectRatio(1f)
            .clip(MaterialTheme.shapes.small)
            .background(colors.bg),
    ) {
        if (image != null) {
            Image(image, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
        IconButton(
            onClick = { model.removePhoto(photo.id) },
            modifier =
                Modifier
                    .align(Alignment.TopEnd)
                    .padding(4.dp)
                    .size(32.dp)
                    .background(colors.plate, CircleShape),
        ) {
            AydaIcon(
                R.drawable.ic_close,
                colors.onPlate,
                size = 16,
                contentDescription = stringResource(R.string.complete_remove_photo, index + 1),
            )
        }
    }
}

/** The attached video or circle, with a button to drop it. */
@Composable
private fun ClipRow(
    clip: PickedClip,
    onRemove: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val circle = clip.kind == CreateUploadRequest.Kind.video_note
    Row(
        Modifier.fillMaxWidth().background(colors.bg, MaterialTheme.shapes.medium).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        AydaIcon(if (circle) R.drawable.ic_camera else R.drawable.ic_play, colors.ink)
        Text(
            stringResource(if (circle) R.string.complete_circle_attached else R.string.complete_video_attached),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = onRemove, modifier = Modifier.size(32.dp).background(colors.plate, CircleShape)) {
            AydaIcon(
                R.drawable.ic_close,
                colors.onPlate,
                size = 16,
                contentDescription =
                    stringResource(if (circle) R.string.complete_remove_circle else R.string.complete_remove_video),
            )
        }
    }
}

/** The picked video, or just over the limit when it is longer: the view model rejects that. */
private fun readVideo(
    resolver: ContentResolver,
    uri: Uri,
): ByteArray? =
    try {
        resolver.openInputStream(uri)?.use { readAtMost(it, MAX_VIDEO_BYTES + 1) }
    } catch (_: IOException) {
        null
    } catch (_: SecurityException) {
        null
    }

private fun readAtMost(
    input: InputStream,
    limit: Int,
): ByteArray {
    val out = ByteArrayOutputStream()
    val buffer = ByteArray(64 * 1024)
    while (out.size() < limit) {
        val read = input.read(buffer, 0, minOf(buffer.size, limit - out.size()))
        if (read < 0) break
        out.write(buffer, 0, read)
    }
    return out.toByteArray()
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.PhotoButton(
    text: String,
    icon: Int = R.drawable.ic_camera,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Button(
        onClick = onClick,
        modifier = Modifier.weight(1f).height(48.dp),
        shape = MaterialTheme.shapes.medium,
        colors = ButtonDefaults.buttonColors(containerColor = colors.bg, contentColor = colors.ink),
    ) {
        AydaIcon(icon, colors.ink, size = 18)
        Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(start = 6.dp))
    }
}

@Composable
private fun Success(
    result: Completion,
    onClose: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val b = result.pointsBreakdown
    Column(
        Modifier.fillMaxWidth().background(colors.accent, MaterialTheme.shapes.large).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            stringResource(R.string.complete_success),
            style = MaterialTheme.typography.headlineSmall,
            color = colors.onAccent,
        )
        Text(
            "+${result.pointsAwarded}",
            style = MaterialTheme.typography.displayLarge.copy(fontSize = 88.sp, lineHeight = 92.sp),
            color = colors.onAccent,
        )
        Text(
            stringResource(
                R.string.complete_breakdown,
                b.base,
                decimal(b.visibilityMultiplier),
                decimal(b.streakMultiplier),
            ),
            style = MaterialTheme.typography.labelLarge,
            color = colors.onAccent,
            textAlign = TextAlign.Center,
        )
        val bonus = result.coopBonus ?: 0
        if (bonus > 0) {
            Text(
                stringResource(R.string.complete_coop_bonus, bonus),
                style = MaterialTheme.typography.titleMedium,
                color = colors.onAccent,
            )
        }
        val days = result.streak.currentDays
        Text(
            stringResource(R.string.complete_streak, days, pluralStringResource(R.plurals.today_days, days)),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.background(colors.surface, MaterialTheme.shapes.small).padding(12.dp, 6.dp),
        )
    }
    PrimaryButton(stringResource(R.string.complete_to_today), onClick = onClose)
}
