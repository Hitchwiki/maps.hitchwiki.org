package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class MapViewModelSelectedTest {
    private fun repoReturning(body: String) = SpotRepository(
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler { respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json")) }
            dispatcher = Dispatchers.Unconfined
        })), "https://example.test"),
        object : SpotCache {
            override suspend fun saveSpots(spots: List<Spot>) {}
            override suspend fun loadSpots(): List<Spot> = emptyList()
        }
    )
    private val noDetail = object : SpotDetailSource {
        override suspend fun detail(sid: String): SpotDetail = SpotDetail()
    }

    @Test fun selectSpotSetsRatingAndCountFromLoadedSpot() = runTest {
        // spot at lat 1.0 lon 2.0 → sid "1.00000_2.00000", rating 4.0, review_count 7
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":7}]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        assertEquals(4.0, vm.state.value.selectedRating)
        assertEquals(7, vm.state.value.selectedReviewCount)
    }
    @Test fun clearSelectionResetsRatingAndCount() = runTest {
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":7}]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        vm.clearSelection()
        assertNull(vm.state.value.selectedRating); assertNull(vm.state.value.selectedReviewCount)
    }
    @Test fun unknownSidLeavesRatingNull() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("9.99999_9.99999"); advanceUntilIdle()
        assertNull(vm.state.value.selectedRating)
    }
}
