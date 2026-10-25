package app.ayda.android.ui.chat

import android.app.TimePickerDialog
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.Coop
import app.ayda.api.models.MeetupOffer
import app.ayda.api.models.MeetupVenue
import app.ayda.shared.plans.MeetupViewModel
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.time.Instant

private val clock = DateTimeFormatter.ofPattern("HH:mm")

@Composable
private fun MeetupVenue.Kind.label(): String =
    stringResource(
        when (this) {
            MeetupVenue.Kind.restaurant -> R.string.meetup_kind_restaurant
            MeetupVenue.Kind.cafe -> R.string.meetup_kind_cafe
            MeetupVenue.Kind.bar -> R.string.meetup_kind_bar
            MeetupVenue.Kind.pub -> R.string.meetup_kind_pub
            MeetupVenue.Kind.fast_food -> R.string.meetup_kind_fast_food
            MeetupVenue.Kind.park -> R.string.meetup_kind_park
            MeetupVenue.Kind.garden -> R.string.meetup_kind_garden
            MeetupVenue.Kind.embankment -> R.string.meetup_kind_embankment
            MeetupVenue.Kind.viewpoint -> R.string.meetup_kind_viewpoint
            MeetupVenue.Kind.square -> R.string.meetup_kind_square
        },
    )

@Composable
private fun MeetupVenue.details(): String {
    val distance =
        if (distanceM < 1000) {
            stringResource(R.string.meetup_distance_m, distanceM)
        } else {
            stringResource(R.string.meetup_distance_km, distanceM / 1000.0)
        }
    val open =
        openNow?.let { stringResource(if (it) R.string.meetup_open else R.string.meetup_closed) }
    return listOfNotNull(kind.label(), address, distance, open).joinToString(" · ")
}

/** US-26: the assistant read the last messages once; the user picks a place (or the online plan). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MeetupSheet(
    model: MeetupViewModel,
    onClose: () -> Unit,
    onCreated: (Coop) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val uri = LocalUriHandler.current
    val offer = state.offer
    val context = LocalContext.current
    val shown = state.startsAt ?: offer?.startsAt
    val time =
        shown?.let {
            clock.format(
                java.time.Instant
                    .ofEpochMilli(it.toEpochMilliseconds())
                    .atZone(ZoneId.systemDefault()),
            )
        }
    ModalBottomSheet(onDismissRequest = onClose, containerColor = colors.bg) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(stringResource(R.string.meetup_title), style = MaterialTheme.typography.headlineSmall)
            if (state.loading) {
                Text(
                    stringResource(R.string.meetup_reading),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
                CircularProgressIndicator(color = colors.accent)
            }
            state.error?.let {
                Text(stringResource(R.string.meetup_failed), style = MaterialTheme.typography.labelLarge)
                TextButton(onClick = model::load) { Text(stringResource(R.string.meetup_retry)) }
            }
            offer?.note?.let { Card { Text(it, style = MaterialTheme.typography.labelLarge) } }
            if (offer != null && time != null && offer.kind != MeetupOffer.Kind.unclear) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(stringResource(R.string.meetup_when, time), style = MaterialTheme.typography.titleMedium)
                    QuietButton(
                        stringResource(R.string.meetup_change_time),
                        onClick = {
                            val (hour, minute) = time.split(":").map(String::toInt)
                            TimePickerDialog(
                                context,
                                { _, h, m ->
                                    val chosen =
                                        LocalDate
                                            .now()
                                            .atTime(h, m)
                                            .atZone(ZoneId.systemDefault())
                                            .toInstant()
                                            .toEpochMilli()
                                    val at = maxOf(chosen, System.currentTimeMillis())
                                    model.setTime(Instant.fromEpochMilliseconds(at))
                                },
                                hour,
                                minute,
                                true,
                            ).show()
                        },
                    )
                }
            }
            if (offer?.kind == MeetupOffer.Kind.online && offer.activity != null) {
                Card {
                    Text(
                        stringResource(R.string.meetup_online, offer.activity!!),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    PrimaryButton(
                        stringResource(R.string.meetup_create_online),
                        onClick = { model.pick(null, onCreated) },
                        enabled = !state.picking,
                    )
                }
            }
            offer?.venues?.forEach { venue ->
                Card {
                    Text(venue.name, style = MaterialTheme.typography.titleMedium)
                    Text(venue.details(), style = MaterialTheme.typography.bodyMedium, color = colors.muted)
                    Text(stringResource(R.string.meetup_reviews), style = MaterialTheme.typography.labelLarge)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(
                            onClick = { uri.openUri(venue.gisUrl) },
                        ) { Text(stringResource(R.string.meetup_gis)) }
                        TextButton(
                            onClick = { uri.openUri(venue.yandexUrl) },
                        ) { Text(stringResource(R.string.meetup_yandex)) }
                    }
                    PrimaryButton(
                        stringResource(R.string.meetup_choose, venue.name),
                        onClick = { model.pick(venue.id, onCreated) },
                        enabled = !state.picking,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            offer?.attribution?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = colors.muted)
            }
        }
    }
}
