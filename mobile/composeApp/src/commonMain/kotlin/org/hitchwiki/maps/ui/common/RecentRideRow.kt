package org.hitchwiki.maps.ui.common
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.model.RecentRide

@Composable
fun RecentRideRow(ride: RecentRide, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp, horizontal = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ride.hitchhikerName ?: "Anonymous", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            RatingStars(ride.rating)
        }
        ride.text?.takeIf { it.isNotBlank() }?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        ride.submissionTime?.let {
            Text(it, style = MaterialTheme.typography.labelSmall)
        }
    }
    HorizontalDivider()
}
