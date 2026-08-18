package org.hitchwiki.maps.ui.search
import org.hitchwiki.maps.data.RecentRidesSource
import org.hitchwiki.maps.model.RecentRide
import kotlinx.coroutines.test.*
import kotlin.test.*

class SearchViewModelTest {
    private class Fake(val list: List<RecentRide>) : RecentRidesSource {
        override suspend fun recent() = list
    }
    private val data = listOf(
        RecentRide(url = "#1.0,2.0", hitchhikerName = "Alice", text = "great ride"),
        RecentRide(url = "#3.0,4.0", hitchhikerName = "Bob", text = "long WAIT"),
        RecentRide(url = "#nope", hitchhikerName = "Carol", text = "unnavigable"),
    )

    @Test fun loadPopulatesRecentDroppingInvalidCoords() = runTest {
        val vm = SearchViewModel(Fake(data), this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(2, vm.state.value.results.size)   // "#nope" dropped
        assertNull(vm.state.value.error)
    }
    @Test fun queryFiltersByNameAndComment_caseInsensitive() = runTest {
        val vm = SearchViewModel(Fake(data), this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.setQuery("alice")
        assertEquals(listOf("Alice"), vm.state.value.results.map { it.hitchhikerName })
        vm.setQuery("wait")   // matches Bob's comment, case-insensitive
        assertEquals(listOf("Bob"), vm.state.value.results.map { it.hitchhikerName })
        vm.setQuery("")       // empty -> all (navigable)
        assertEquals(2, vm.state.value.results.size)
    }
    @Test fun failureSetsErrorNotStuckLoading() = runTest {
        val failing = object : RecentRidesSource {
            override suspend fun recent(): List<RecentRide> = throw RuntimeException("boom")
        }
        val vm = SearchViewModel(failing, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertNotNull(vm.state.value.error)
    }
}
