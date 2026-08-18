package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilterSheet(current: FilterState, onApply: (FilterState) -> Unit, onDismiss: () -> Unit) {
    // Local edit copy; committed to the map on each change via onApply so the markers update live.
    var draft by remember(current) { mutableStateOf(current) }
    fun update(next: FilterState) { draft = next; onApply(next) }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("Filters", style = MaterialTheme.typography.titleMedium)

            Text("Minimum rating", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.labelLarge)
            Row(Modifier.padding(top = 4.dp)) {
                listOf(0 to "Any", 3 to "3+", 4 to "4+", 5 to "5").forEach { (value, label) ->
                    FilterChip(
                        selected = draft.minRating == value,
                        onClick = { update(draft.copy(minRating = value)) },
                        label = { Text(label) },
                        modifier = Modifier.padding(end = 8.dp),
                    )
                }
            }

            FilterToggle("Official spot (OSM)", draft.osm) { update(draft.copy(osm = it)) }
            FilterToggle("On Hitchwiki", draft.wiki) { update(draft.copy(wiki = it)) }
            FilterToggle("Car-pooling nearby", draft.cp) { update(draft.copy(cp = it)) }
            FilterToggle("At a gas station", draft.fuel) { update(draft.copy(fuel = it)) }

            TextButton(onClick = { update(FilterState()) }, modifier = Modifier.padding(top = 8.dp)) {
                Text("Reset")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun FilterToggle(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(top = 8.dp).selectable(checked) { onCheckedChange(!checked) },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}
