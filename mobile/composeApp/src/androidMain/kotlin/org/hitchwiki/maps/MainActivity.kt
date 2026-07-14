package org.hitchwiki.maps
import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.lifecycle.lifecycleScope
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.launch
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.db.HitchwikiDb
import org.hitchwiki.maps.location.LocationProvider
import org.hitchwiki.maps.ui.map.MapScreen
import org.hitchwiki.maps.ui.map.MapViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Build the P1 data graph. DatabaseDriverFactory's Android actual takes a Context.
        val db = HitchwikiDb(DatabaseDriverFactory(applicationContext).create())
        val api = HitchwikiApi(defaultHttpClient(OkHttp.create()))
        val repository = SpotRepository(api, SqlDelightSpotCache(db))
        val details = ApiSpotDetailSource(api)
        val viewModel = MapViewModel(repository, details, lifecycleScope)
        val locationProvider = LocationProvider(applicationContext)

        val permissionLauncher = registerForActivityResult(
            ActivityResultContracts.RequestPermission()
        ) { granted ->
            if (granted) lifecycleScope.launch {
                locationProvider.current()?.let { viewModel.onUserLocation(it) }
            }
        }

        setContent {
            MaterialTheme {
                MapScreen(
                    viewModel = viewModel,
                    onRequestLocation = { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                )
            }
        }
    }
}
