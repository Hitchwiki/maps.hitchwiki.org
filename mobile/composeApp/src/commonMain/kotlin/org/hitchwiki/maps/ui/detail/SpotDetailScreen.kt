package org.hitchwiki.maps.ui.detail
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.ridesNewestFirst
import org.hitchwiki.maps.data.spotLinks
import org.hitchwiki.maps.ui.common.RatingStars
import org.hitchwiki.maps.ui.common.RideCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpotDetailScreen(viewModel: SpotDetailViewModel, rating: Float, reviewCount: Int, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val uriHandler = LocalUriHandler.current
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Spot") },
            navigationIcon = { IconButton(onClick = onBack) { Text("‹") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize().padding(horizontal = 16.dp)) {
            item {
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, modifier = Modifier.padding(vertical = 8.dp)) {
                    RatingStars(kotlin.math.round(rating).toInt())
                    Spacer(Modifier.width(8.dp))
                    Text("$reviewCount reviews", style = MaterialTheme.typography.labelMedium)
                }
                val d = state.detail
                d?.spot?.wait?.let { Text("Avg wait: $it min") }
                d?.spot?.distance?.let { Text("Avg ride: $it km") }
                d?.spot?.let { info ->
                    spotLinks(info).forEach { link ->
                        TextButton(onClick = { uriHandler.openUri(link.url) }) { Text("${link.emoji} ${link.label}") }
                    }
                }
                when {
                    state.loading -> Text("Loading…", Modifier.padding(vertical = 8.dp))
                    state.error != null -> Text("Couldn't load this spot.", Modifier.padding(vertical = 8.dp))
                    d != null && d.rides.isEmpty() -> Text("No rides logged here yet.", Modifier.padding(vertical = 8.dp))
                }
            }
            state.detail?.let { d ->
                items(ridesNewestFirst(d.rides)) { ride -> RideCard(ride) }
            }
        }
    }
}
