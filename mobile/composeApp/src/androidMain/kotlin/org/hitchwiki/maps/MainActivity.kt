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
import org.hitchwiki.maps.ui.AppNav
import org.hitchwiki.maps.ui.map.MapViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // DIAGNOSTICS ONLY: log any uncaught throwable (from any thread) before delegating to
        // the previous handler, so an unreproduced first-run crash leaves a trace in logcat.
        // Behavior is unchanged -- the previous handler still runs afterwards.
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            android.util.Log.e("HitchwikiCrash", "Uncaught on ${thread.name}", throwable)
            prev?.uncaughtException(thread, throwable)
        }

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

        // Initial camera: if location permission is ALREADY granted, center on last-known location
        // without prompting (the FAB still owns the request flow). Otherwise the map opens at its
        // default world view.
        val hasLoc = androidx.core.content.ContextCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED ||
            androidx.core.content.ContextCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_COARSE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
        if (hasLoc) {
            lifecycleScope.launch { locationProvider.current()?.let { viewModel.onUserLocation(it) } }
        }

        setContent {
            MaterialTheme {
                AppNav(
                    mapViewModel = viewModel,
                    detailSource = details,
                    scope = lifecycleScope,
                    onRequestLocation = { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                )
            }
        }
    }
}
