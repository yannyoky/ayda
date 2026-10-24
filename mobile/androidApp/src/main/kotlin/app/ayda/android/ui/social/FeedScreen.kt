package app.ayda.android.ui.social

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.chat.PlayableVideo
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.label
import app.ayda.api.models.Me
import app.ayda.api.models.Photo
import app.ayda.api.models.Post
import app.ayda.api.models.PostVideo
import app.ayda.shared.social.CommentsState
import app.ayda.shared.social.FeedViewModel
import coil3.compose.AsyncImage

/** US-13: proofs and routines of me and my friends, newest first. */
@Composable
fun FeedScreen(
    model: FeedViewModel,
    me: Me,
    contentPadding: PaddingValues,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    LifecycleResumeEffect(model) {
        model.refresh()
        onPauseOrDispose {}
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().background(colors.bg).safeDrawingPadding(),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                stringResource(R.string.feed_title),
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
        state.error?.let { error ->
            item {
                Card {
                    Text(error, style = MaterialTheme.typography.bodyLarge)
                    PrimaryButton(stringResource(R.string.retry), onClick = {
                        model.dismissError()
                        model.refresh()
                    })
                }
            }
        }
        if (state.empty) {
            item {
                Card {
                    Text(
                        stringResource(R.string.feed_empty),
                        style = MaterialTheme.typography.bodyLarge,
                        color = colors.muted,
                    )
                }
            }
        }
        items(state.posts, key = { it.id }) { post ->
            PostCard(
                post,
                mine = post.author.id == me.id,
                onLike = { model.toggleLike(post.id) },
                onComments = { model.openComments(post.id) },
                onDelete = { model.askDelete(post) },
                onVideoExpired = model::refresh,
            )
        }
        if (state.hasMore) {
            item {
                Button(
                    onClick = model::loadMore,
                    enabled = !state.loadingMore,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = MaterialTheme.shapes.medium,
                    colors = ButtonDefaults.buttonColors(containerColor = colors.surface, contentColor = colors.ink),
                ) { Text(stringResource(R.string.feed_more), style = MaterialTheme.typography.titleMedium) }
            }
        }
    }
    state.comments?.let { CommentsSheet(it, model) }
    if (state.deleting != null) {
        AlertDialog(
            onDismissRequest = model::cancelDelete,
            text = { Text(stringResource(R.string.feed_delete_confirm)) },
            confirmButton = {
                TextButton(
                    onClick = model::confirmDelete,
                ) { Text(stringResource(R.string.feed_delete_yes)) }
            },
            dismissButton = { TextButton(onClick = model::cancelDelete) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun PostCard(
    post: Post,
    mine: Boolean,
    onLike: () -> Unit,
    onComments: () -> Unit,
    onDelete: () -> Unit,
    onVideoExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val routine = post.kind == Post.Kind.routine
    val category = stringResource(post.category.label())
    val name = if (mine) stringResource(R.string.feed_me) else post.author.firstName
    val what = if (routine) stringResource(R.string.feed_routine) else post.questTitle ?: category
    Column(
        Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Avatar(post.author)
            Column(Modifier.weight(1f)) {
                Text(name, style = MaterialTheme.typography.titleMedium)
                Text(
                    "$what · ${formatAgo(post.createdAt)}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                category,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.background(colors.bg, MaterialTheme.shapes.small).padding(10.dp, 4.dp),
            )
        }
        if (routine) {
            Row(
                Modifier.fillMaxWidth().background(colors.bg, RoundedCornerShape(18.dp)).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                AydaIcon(R.drawable.ic_lock, colors.muted)
                Text(
                    stringResource(R.string.feed_routine_hidden),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
            }
        } else {
            if (post.photos.isNotEmpty()) Photos(post.photos)
            post.video?.let { ProofVideo(it, onVideoExpired) }
            post.caption?.let {
                Text(it, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(horizontal = 4.dp))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val likeLabel =
                if (post.likedByMe) {
                    stringResource(R.string.feed_unlike, post.likeCount)
                } else {
                    stringResource(R.string.feed_like, post.likeCount)
                }
            CountButton(
                icon = if (post.likedByMe) R.drawable.ic_heart_filled else R.drawable.ic_heart,
                count = post.likeCount,
                label = likeLabel,
                active = post.likedByMe,
                onClick = onLike,
            )
            CountButton(
                icon = R.drawable.ic_comment,
                count = post.commentCount,
                label = stringResource(R.string.feed_comments, post.commentCount),
                active = false,
                onClick = onComments,
            )
            Spacer(Modifier.weight(1f))
            if (mine) {
                IconButton(onClick = onDelete) {
                    AydaIcon(
                        R.drawable.ic_trash,
                        colors.muted,
                        size = 18,
                        contentDescription = stringResource(R.string.feed_delete),
                    )
                }
            }
        }
    }
}

@Composable
private fun CountButton(
    icon: Int,
    count: Int,
    label: String,
    active: Boolean,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val content = if (active) colors.onAccent else colors.ink
    Button(
        onClick = onClick,
        modifier = Modifier.height(44.dp).semantics { contentDescription = label },
        shape = MaterialTheme.shapes.medium,
        contentPadding = PaddingValues(horizontal = 14.dp),
        colors =
            ButtonDefaults.buttonColors(
                containerColor = if (active) colors.accent else colors.bg,
                contentColor = content,
            ),
    ) {
        AydaIcon(icon, content, size = 18)
        Spacer(Modifier.width(6.dp))
        Text("$count", style = MaterialTheme.typography.titleMedium)
    }
}

/** A proof's video or circle (ADR 0019); the file is deleted 30 days after upload. */
@Composable
private fun ProofVideo(
    video: PostVideo,
    onExpired: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val note = video.kind == PostVideo.Kind.video_note
    val url = video.url
    if (video.status != PostVideo.Status.ready || url == null) {
        val text =
            when (video.status) {
                PostVideo.Status.expired -> if (note) R.string.chats_circle_expired else R.string.feed_video_expired
                PostVideo.Status.failed -> if (note) R.string.chats_circle_failed else R.string.feed_video_failed
                else -> if (note) R.string.chats_circle_processing else R.string.feed_video_processing
            }
        Text(
            stringResource(text),
            style = MaterialTheme.typography.labelLarge,
            color = colors.muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().background(colors.bg, RoundedCornerShape(20.dp)).padding(24.dp),
        )
        return
    }
    if (note) {
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            PlayableVideo(
                url,
                video.durationMs,
                CircleShape,
                stringResource(R.string.chats_circle_play),
                onExpired,
                modifier = Modifier.size(220.dp),
            )
        }
        return
    }
    val width = video.width ?: 16
    val height = video.height ?: 9
    PlayableVideo(
        url,
        video.durationMs,
        RoundedCornerShape(20.dp),
        stringResource(R.string.feed_video_play),
        onExpired,
        modifier = Modifier.fillMaxWidth().aspectRatio((width.toFloat() / height).coerceIn(0.56f, 1.8f)),
    )
}

@Composable
private fun Photos(photos: List<Photo>) {
    val colors = LocalAydaColors.current
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        itemsIndexed(photos, key = { _, photo -> photo.id }) { index, photo ->
            AsyncImage(
                model = privateImage(photo.url),
                contentDescription = stringResource(R.string.feed_photo, index + 1, photos.size),
                contentScale = ContentScale.Crop,
                modifier =
                    Modifier
                        .fillParentMaxWidth(if (photos.size > 1) 0.88f else 1f)
                        .aspectRatio(4f / 3f)
                        .clip(RoundedCornerShape(20.dp))
                        .background(colors.plate),
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CommentsSheet(
    state: CommentsState,
    model: FeedViewModel,
) {
    val colors = LocalAydaColors.current
    ModalBottomSheet(onDismissRequest = model::closeComments, containerColor = colors.bg) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding()
                .imePadding(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(stringResource(R.string.comments_title), style = MaterialTheme.typography.headlineSmall)
            if (state.loaded && state.items.isEmpty()) {
                Text(
                    stringResource(R.string.comments_empty),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            }
            LazyColumn(Modifier.weight(1f, fill = false), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.items, key = { it.id }) { comment ->
                    Row(
                        Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.medium).padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Avatar(comment.author, size = 32)
                        Column(Modifier.weight(1f)) {
                            Text(
                                "${comment.author.firstName} · ${formatAgo(comment.createdAt)}",
                                style = MaterialTheme.typography.labelLarge,
                                color = colors.muted,
                            )
                            Text(comment.text, style = MaterialTheme.typography.bodyLarge)
                        }
                        if (comment.canDelete) {
                            IconButton(onClick = { model.deleteComment(comment) }, modifier = Modifier.size(36.dp)) {
                                AydaIcon(
                                    R.drawable.ic_close,
                                    colors.muted,
                                    size = 16,
                                    contentDescription = stringResource(R.string.comments_delete),
                                )
                            }
                        }
                    }
                }
            }
            state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = state.text,
                    onValueChange = model::onCommentTextChange,
                    placeholder = { Text(stringResource(R.string.comments_placeholder)) },
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = model::sendComment,
                    enabled = state.canSend,
                    modifier = Modifier.size(52.dp).clip(MaterialTheme.shapes.medium).background(colors.accent),
                ) {
                    AydaIcon(
                        R.drawable.ic_arrow,
                        colors.onAccent,
                        contentDescription = stringResource(R.string.comments_send),
                    )
                }
            }
        }
    }
}
