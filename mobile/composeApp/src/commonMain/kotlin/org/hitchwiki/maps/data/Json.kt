package org.hitchwiki.maps.data
import kotlinx.serialization.json.Json
// ignoreUnknownKeys: dist/ files may gain fields; the app must not crash on them.
// Deliberately NOT lenient: leniency would coerce a JSON int into a String field (or vice
// versa) without complaint, silently masking model/backend type drift. We want that to fail
// loudly at parse time instead.
val appJson: Json = Json { ignoreUnknownKeys = true }
