package org.hitchwiki.maps.data
import kotlinx.serialization.json.Json
// ignoreUnknownKeys: dist/ files may gain fields; the app must not crash on them.
val appJson: Json = Json { ignoreUnknownKeys = true; isLenient = true }
