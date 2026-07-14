package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.*
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class MapViewModelTest {
    private fun repoReturning(body: String) = SpotRepository(
        // MapViewModel.load()/selectSpot() run the repository call inside `scope.launch`, so the
        // test only observes completion via advanceUntilIdle(). MockEngine's default dispatcher is
        // a real Dispatchers.IO, which hops to a background thread the TestCoroutineScheduler can't
        // see or wait for — advanceUntilIdle() would return before that thread posts its result back,
        // failing deterministically. Pinning the engine to Dispatchers.Unconfined keeps request
        // handling on the test dispatcher so advanceUntilIdle() can observe it complete.
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler { respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json")) }
            dispatcher = Dispatchers.Unconfined
        })), "https://example.test"),
        object : SpotCache { // trivial no-op cache; network path is what we exercise
            override suspend fun saveSpots(spots: List<Spot>) {}
            override suspend fun loadSpots(): List<Spot> = emptyList()
        }
    )
    private class FakeDetails(val detail: SpotDetail) : SpotDetailSource {
        var requested: String? = null
        override suspend fun detail(sid: String): SpotDetail { requested = sid; return detail }
    }

    @Test fun loadPopulatesSpotsAndGeoJson() = runTest {
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":3}]"""),
            FakeDetails(SpotDetail()), this)
        vm.load(); advanceUntilIdle()
        val s = vm.state.value
        assertFalse(s.loading); assertEquals(1, s.spots.size)
        assertTrue(s.geoJson.contains("\"FeatureCollection\""))
        assertNull(s.error)
    }
    @Test fun selectSpotLoadsDetail() = runTest {
        val det = SpotDetail(spot = SpotInfo(wait = 12), rides = emptyList())
        val fake = FakeDetails(det)
        val vm = MapViewModel(repoReturning("""[]"""), fake, this)
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        val s = vm.state.value
        assertEquals("1.00000_2.00000", s.selectedSid)
        assertEquals("1.00000_2.00000", fake.requested)
        assertEquals(12, s.selectedDetail?.spot?.wait)
        assertFalse(s.detailLoading)
    }
    @Test fun clearSelectionResetsDetail() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), FakeDetails(SpotDetail()), this)
        vm.selectSpot("x"); advanceUntilIdle()
        vm.clearSelection()
        assertNull(vm.state.value.selectedSid); assertNull(vm.state.value.selectedDetail)
    }
    @Test fun onUserLocationSetsCameraAndLocation() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), FakeDetails(SpotDetail()), this)
        vm.onUserLocation(LatLng(48.0, 11.0))
        assertEquals(LatLng(48.0, 11.0), vm.state.value.userLocation)
        assertEquals(LatLng(48.0, 11.0), vm.state.value.cameraTarget)
    }
    @Test fun selectSpotDetailFailureSetsErrorNotStuckLoading() = runTest {
        val failing = object : org.hitchwiki.maps.data.SpotDetailSource {
            override suspend fun detail(sid: String): org.hitchwiki.maps.model.SpotDetail = throw RuntimeException("boom")
        }
        val vm = MapViewModel(repoReturning("""[]"""), failing, this)
        vm.selectSpot("x"); advanceUntilIdle()
        val s = vm.state.value
        assertFalse(s.detailLoading)        // not stuck loading
        assertNull(s.selectedDetail)
        assertNotNull(s.detailError)        // error surfaced
    }
}
