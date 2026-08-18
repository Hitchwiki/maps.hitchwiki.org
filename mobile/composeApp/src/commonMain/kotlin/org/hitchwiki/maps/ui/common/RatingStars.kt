package org.hitchwiki.maps.ui.common
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun RatingStars(rating: Int?, modifier: Modifier = Modifier) {
    // Filled/empty stars for a 1..5 rating; nothing when unrated.
    val r = rating?.coerceIn(0, 5) ?: return
    Text("★".repeat(r) + "☆".repeat(5 - r), modifier = modifier)
}
