package org.hitchwiki.maps.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import kotlinx.coroutines.CoroutineScope
import org.hitchwiki.maps.data.RecentRidesSource
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.ui.detail.SpotDetailScreen
import org.hitchwiki.maps.ui.detail.SpotDetailViewModel
import org.hitchwiki.maps.ui.map.MapScreen
import org.hitchwiki.maps.ui.map.MapViewModel
import org.hitchwiki.maps.ui.search.SearchScreen
import org.hitchwiki.maps.ui.search.SearchViewModel

/**
 * Top-level navigation graph: the map is the start destination, and tapping a marker's
 * "Full detail" action pushes the spot-detail screen. Route args carry the rating/review-count
 * shown on the map (spots.json/rides_index.json don't expose an aggregate elsewhere), while the
 * spot id also seeds a fresh SpotDetailViewModel per destination.
 */
@Composable
fun AppNav(
    mapViewModel: MapViewModel,
    detailSource: SpotDetailSource,
    recentSource: RecentRidesSource,
    scope: CoroutineScope,
    onRequestLocation: () -> Unit,
) {
    val nav = rememberNavController()
    NavHost(nav, startDestination = "map") {
        composable("map") {
            MapScreen(
                viewModel = mapViewModel,
                onRequestLocation = onRequestLocation,
                onOpenDetail = { sid, rating, count -> nav.navigate("spot/$sid?rating=$rating&count=$count") },
                onOpenSearch = { nav.navigate("search") },
            )
        }
        composable("search") {
            val vm = remember { SearchViewModel(recentSource, scope) }
            SearchScreen(
                viewModel = vm,
                onResult = { lat, lon, sid -> mapViewModel.focusSpot(lat, lon, sid); nav.popBackStack() },
                onBack = { nav.popBackStack() },
            )
        }
        composable(
            route = "spot/{sid}?rating={rating}&count={count}",
            arguments = listOf(
                navArgument("sid") { type = NavType.StringType },
                navArgument("rating") { type = NavType.FloatType; defaultValue = 0f },
                navArgument("count") { type = NavType.IntType; defaultValue = 0 },
            ),
        ) { entry ->
            val sid = entry.arguments?.getString("sid") ?: return@composable
            val rating = entry.arguments?.getFloat("rating") ?: 0f
            val count = entry.arguments?.getInt("count") ?: 0
            // Fresh detail VM per navigation to this spot; remember it against the sid.
            val vm = remember(sid) { SpotDetailViewModel(sid, detailSource, scope) }
            SpotDetailScreen(viewModel = vm, rating = rating, reviewCount = count, onBack = { nav.popBackStack() })
        }
    }
}
