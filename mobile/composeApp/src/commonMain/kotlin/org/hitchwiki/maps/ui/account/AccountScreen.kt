package org.hitchwiki.maps.ui.account
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.AuthStatus

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountScreen(viewModel: AccountViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Account") },
            navigationIcon = { TextButton(onClick = onBack) { Text("Back") } },
        )
    }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            when (val s = state.status) {
                is AuthStatus.SignedIn -> {
                    Text("Signed in as", style = MaterialTheme.typography.labelLarge)
                    Text(s.username, style = MaterialTheme.typography.headlineSmall)
                    Spacer(Modifier.height(24.dp))
                    OutlinedButton(onClick = { viewModel.logout() }, enabled = !state.loading) {
                        Text("Log out")
                    }
                }
                else -> {
                    Text("Sign in to log rides with your Hitchwiki account.",
                        style = MaterialTheme.typography.bodyLarge)
                    Spacer(Modifier.height(24.dp))
                    Button(onClick = { viewModel.signIn() }, enabled = !state.loading) {
                        Text("Sign in with Hitchwiki")
                    }
                }
            }
            state.error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }
            if (state.loading) {
                Spacer(Modifier.height(16.dp))
                CircularProgressIndicator()
            }
        }
    }
}
