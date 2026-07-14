package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.model.SpotDetail
import org.hitchwiki.maps.model.SpotInfo
import kotlinx.coroutines.test.*
import kotlin.test.*

class SpotDetailViewModelTest {
    private fun source(result: () -> SpotDetail) = object : SpotDetailSource {
        override suspend fun detail(sid: String): SpotDetail = result()
    }
    @Test fun loadFetchesDetail() = runTest {
        val vm = SpotDetailViewModel("sid1", source { SpotDetail(spot = SpotInfo(wait = 9)) }, this)
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(9, vm.state.value.detail?.spot?.wait)
        assertNull(vm.state.value.error)
    }
    @Test fun loadFailureSetsError() = runTest {
        val vm = SpotDetailViewModel("sid1", source { throw RuntimeException("boom") }, this)
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertNull(vm.state.value.detail)
        assertNotNull(vm.state.value.error)
    }
}
