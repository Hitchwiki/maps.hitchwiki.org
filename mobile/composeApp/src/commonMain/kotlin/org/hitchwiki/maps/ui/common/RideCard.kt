package org.hitchwiki.maps.ui.common
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.model.SpotRide
import org.hitchwiki.maps.util.formatRideDate

@Composable
fun RideCard(ride: SpotRide, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                RatingStars(ride.rating)
                Spacer(Modifier.weight(1f))
                Text(ride.hitchhikerName, style = MaterialTheme.typography.labelMedium)
            }
            val date = formatRideDate(ride.submissionTime)
            val meta = buildList {
                if (date.isNotEmpty()) add(date)
                ride.wait?.let { add("waited $it min") }
                ride.distance?.let { add("$it km") }
            }.joinToString(" · ")
            if (meta.isNotEmpty()) Text(meta, style = MaterialTheme.typography.bodySmall)
            ride.comment?.let { Text(it, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp)) }
        }
    }
}
