package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.ridesNewestFirst
import org.hitchwiki.maps.ui.common.RatingStars
import org.hitchwiki.maps.ui.common.RideCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpotSummarySheet(state: MapUiState, onDismiss: () -> Unit, onOpenDetail: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                RatingStars(state.selectedRating?.let { kotlin.math.round(it).toInt() })
                Spacer(Modifier.width(8.dp))
                state.selectedReviewCount?.let { Text("$it reviews", style = MaterialTheme.typography.labelMedium) }
            }
            when {
                state.detailLoading -> Text("Loading…", Modifier.padding(top = 8.dp))
                state.detailError != null -> Text("Couldn't load spot details.", Modifier.padding(top = 8.dp))
                state.selectedDetail != null -> {
                    val d = state.selectedDetail!!
                    d.spot.wait?.let { Text("Avg wait: $it min", Modifier.padding(top = 8.dp)) }
                    ridesNewestFirst(d.rides).take(3).forEach { RideCard(it) }
                    if (d.rides.size > 3) {
                        TextButton(onClick = onOpenDetail, modifier = Modifier.padding(top = 4.dp)) {
                            Text("Full detail (${d.rides.size} rides)")
                        }
                    } else {
                        TextButton(onClick = onOpenDetail, modifier = Modifier.padding(top = 4.dp)) { Text("Full detail") }
                    }
                }
                else -> Text("No details available.", Modifier.padding(top = 8.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
