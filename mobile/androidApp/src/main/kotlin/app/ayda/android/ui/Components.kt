package app.ayda.android.ui

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.shared.Motion
import app.ayda.shared.Radii

/** `--ease-out` of docs/design/themes.md: most of the move happens at once, then it settles. */
val EaseOutQuint = CubicBezierEasing(0.23f, 1f, 0.32f, 1f)

/**
 * Press feedback (docs/design/themes.md, "Motion"): the scale a pressable thing has right now,
 * 0.97 under the finger. With "Remove animations" on, Compose snaps it, so nothing moves.
 */
@Composable
fun pressScale(source: InteractionSource): Float {
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(
        if (pressed) Motion.PRESSED_SCALE else 1f,
        tween(Motion.PRESS, easing = EaseOutQuint),
        label = "press",
    )
    return scale
}

/** A Material button that shrinks a little under the finger; every Ayda button goes through it. */
@Composable
fun PressButton(
    onClick: () -> Unit,
    containerColor: Color,
    contentColor: Color,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    shape: Shape = MaterialTheme.shapes.medium,
    contentPadding: PaddingValues = ButtonDefaults.ContentPadding,
    content: @Composable RowScope.() -> Unit,
) {
    val colors = LocalAydaColors.current
    val source = remember { MutableInteractionSource() }
    val scale = pressScale(source)
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = shape,
        contentPadding = contentPadding,
        interactionSource = source,
        modifier =
            modifier.graphicsLayer {
                scaleX = scale
                scaleY = scale
            },
        colors =
            ButtonDefaults.buttonColors(
                containerColor = containerColor,
                contentColor = contentColor,
                disabledContainerColor = colors.track,
                disabledContentColor = colors.muted,
            ),
        content = content,
    )
}

/** A bento card on the screen background. */
@Composable
fun Card(
    modifier: Modifier = Modifier,
    color: Color = LocalAydaColors.current.surface,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier =
            modifier
                .fillMaxWidth()
                .background(color, MaterialTheme.shapes.large)
                .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        content = content,
    )
}

/** The accent call to action. */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val colors = LocalAydaColors.current
    PressButton(
        onClick = onClick,
        enabled = enabled,
        containerColor = colors.accent,
        contentColor = colors.onAccent,
        modifier = modifier.fillMaxWidth().height(52.dp),
    ) {
        Text(text, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
fun QuietButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    color: Color = LocalAydaColors.current.ink,
) {
    TextButton(onClick = onClick, modifier = modifier) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = color)
    }
}

/**
 * A segmented control with one pill that slides to the chosen option instead of jumping
 * (docs/design/themes.md: 250ms). Options share the width equally.
 */
@Composable
fun <T> Segmented(
    options: List<Pair<T, String>>,
    selected: T,
    onSelect: (T) -> Unit,
    modifier: Modifier = Modifier,
    track: Color = LocalAydaColors.current.surface,
    pill: Color = LocalAydaColors.current.plate,
    selectedText: Color = LocalAydaColors.current.onPlate,
    text: Color = LocalAydaColors.current.muted,
) {
    val index = options.indexOfFirst { it.first == selected }.coerceAtLeast(0)
    BoxWithConstraints(
        modifier
            .fillMaxWidth()
            .height(48.dp)
            .background(track, RoundedCornerShape(Radii.FIELD.dp))
            .padding(4.dp),
    ) {
        val gap = 6.dp
        val width = (maxWidth - gap * (options.size - 1)) / options.size
        val offset by animateDpAsState(
            (width + gap) * index,
            tween(Motion.SEGMENT, easing = EaseOutQuint),
            label = "segment",
        )
        Box(
            Modifier
                .offset { IntOffset(offset.roundToPx(), 0) }
                .width(width)
                .fillMaxHeight()
                .background(pill, RoundedCornerShape(Radii.SEGMENT.dp)),
        )
        Row(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(gap)) {
            options.forEachIndexed { i, (value, label) ->
                Box(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .selectable(selected = i == index, role = Role.RadioButton, onClick = { onSelect(value) }),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        label,
                        style = MaterialTheme.typography.labelLarge,
                        color = if (i == index) selectedText else text,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

/** The assistant's face: a spark on the accent tile, so her chat never looks like a friend's. */
@Composable
fun AydaMark(size: Int = 40) {
    val colors = LocalAydaColors.current
    Box(
        Modifier.size(size.dp).background(colors.accent, RoundedCornerShape((size * 0.35f).dp)),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            painterResource(R.drawable.ic_spark_filled),
            contentDescription = null,
            tint = colors.onAccent,
            modifier = Modifier.size((size * 0.5f).dp),
        )
    }
}
