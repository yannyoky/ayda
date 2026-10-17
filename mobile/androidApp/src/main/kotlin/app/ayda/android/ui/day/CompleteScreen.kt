package app.ayda.android.ui.day

import android.content.ActivityNotFoundException
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
import androidx.compose.runtime.getValue
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
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.media.PhotoCompressor
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.api.models.Completion
import app.ayda.api.models.Visibility
import app.ayda.shared.day.CompleteState
import app.ayda.shared.day.CompleteViewModel
import app.ayda.shared.day.PhotoError
import app.ayda.shared.day.PickedPhoto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** US-09/US-10: mark a taken quest done, choose who sees it, attach 1-3 photos for friends. */
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
        listOf(Visibility.friends, Visibility.routine, Visibility.personal).forEach { visibility ->
            VisibilityOption(
                visibility,
                selected = state.visibility == visibility,
                points = model.expectedPoints(visibility),
                onSelect = { model.onVisibilityChange(visibility) },
            )
        }
        if (state.needPhotos) PhotoSection(state, model)
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
        val upload = state.uploading
        PrimaryButton(
            if (upload != null) {
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
            Visibility.friends -> R.string.complete_friends to R.string.complete_friends_text
            Visibility.routine -> R.string.complete_routine to R.string.complete_routine_text
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
        if (state.canAddPhoto) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PhotoButton(stringResource(R.string.complete_gallery)) {
                    gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }
                PhotoButton(stringResource(R.string.complete_camera)) {
                    val dir = File(context.cacheDir, "camera").apply { mkdirs() }
                    val file = File(dir, "shot-${System.currentTimeMillis()}.jpg")
                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.photos", file)
                    shot = uri.toString()
                    try {
                        camera.launch(uri)
                    } catch (_: ActivityNotFoundException) {
                        shot = null
                        model.photoFailed()
                    }
                }
            }
        }
        Text(
            when (state.photoError) {
                PhotoError.TooBig -> stringResource(R.string.complete_photo_too_big)
                PhotoError.Unreadable -> stringResource(R.string.complete_photo_unreadable)
                null -> stringResource(R.string.complete_photos_hint)
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

@Composable
private fun androidx.compose.foundation.layout.RowScope.PhotoButton(
    text: String,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Button(
        onClick = onClick,
        modifier = Modifier.weight(1f).height(48.dp),
        shape = MaterialTheme.shapes.medium,
        colors = ButtonDefaults.buttonColors(containerColor = colors.bg, contentColor = colors.ink),
    ) {
        AydaIcon(R.drawable.ic_camera, colors.ink, size = 18)
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
