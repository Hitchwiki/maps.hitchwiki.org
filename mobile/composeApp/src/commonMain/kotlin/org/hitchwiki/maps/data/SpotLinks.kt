package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotInfo

data class SpotLink(val emoji: String, val label: String, val url: String)

// Present links only, in a fixed display order. URLs match the web spot pane exactly.
fun spotLinks(spot: SpotInfo): List<SpotLink> = buildList {
    spot.osmId?.let { add(SpotLink("🚏", "Official hitchhiking spot", "https://www.openstreetmap.org/node/$it")) }
    spot.carPooling?.let { add(SpotLink("🚗", "Car pooling spot", "https://www.openstreetmap.org/${it.osmType}/${it.id}")) }
    spot.fuel?.let { add(SpotLink("⛽", "Gas station", "https://www.openstreetmap.org/${it.osmType}/${it.id}")) }
    spot.hitchwikiArticle?.let { add(SpotLink("📄", "Mentioned on Hitchwiki", it)) }
    spot.hitchwikiMap?.let { add(SpotLink("🗺️", "On Hitchwiki", it)) }
}
