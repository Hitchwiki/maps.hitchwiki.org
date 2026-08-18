package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.Spot
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.*
import kotlin.test.*

class MapViewModelFilterTest {
    // Two spots: one 5-star OSM, one 2-star non-OSM.
    private val body = """[{"lat":1.0,"lon":2.0,"rating":5.0,"review_count":1,"osm":true},
                           {"lat":3.0,"lon":4.0,"rating":2.0,"review_count":1}]"""
    private fun repo() = SpotRepository(
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
        override suspend fun detail(sid: String) = org.hitchwiki.maps.model.SpotDetail()
    }
    private fun featureCount(geoJson: String) =
        appJson.parseToJsonElement(geoJson).jsonObject["features"]!!.jsonArray.size

    @Test fun setFilterNarrowsGeoJsonToSubset() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertEquals(2, featureCount(vm.state.value.geoJson))
        vm.setFilter(FilterState(minRating = 4)); advanceUntilIdle()
        assertEquals(1, featureCount(vm.state.value.geoJson))
        assertEquals(FilterState(minRating = 4), vm.state.value.filterState)
    }
    @Test fun clearingFilterRestoresAll() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.setFilter(FilterState(osm = true)); advanceUntilIdle()
        assertEquals(1, featureCount(vm.state.value.geoJson))
        vm.setFilter(FilterState()); advanceUntilIdle()
        assertEquals(2, featureCount(vm.state.value.geoJson))
    }
    @Test fun focusSpotSetsCameraAndSelection() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.focusSpot(3.0, 4.0, "3.00000_4.00000"); advanceUntilIdle()
        assertEquals(LatLng(3.0, 4.0), vm.state.value.cameraTarget)
        assertEquals("3.00000_4.00000", vm.state.value.selectedSid)
    }
}
