package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.data.AuthRepository
import org.hitchwiki.maps.data.AuthStatus
import org.hitchwiki.maps.data.SignInOutcome
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AccountViewModel(
    private val repo: AuthRepository,
    private val scope: CoroutineScope,
    private val workDispatcher: CoroutineDispatcher = Dispatchers.Default,
) {
    private val _state = MutableStateFlow(AccountUiState())
    val state: StateFlow<AccountUiState> = _state.asStateFlow()

    /** Validate on open. Unknown/offline keeps the last state rather than showing an error. */
    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            val status = withContext(workDispatcher) { repo.currentUser() }
            _state.update { it.copy(loading = false, status = status) }
        }
    }

    fun signIn() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            when (val outcome = withContext(workDispatcher) { repo.signIn() }) {
                is SignInOutcome.Success ->
                    _state.update { it.copy(loading = false, status = AuthStatus.SignedIn(outcome.username)) }
                is SignInOutcome.Cancelled ->
                    _state.update { it.copy(loading = false, status = AuthStatus.SignedOut) }
                is SignInOutcome.Failed ->
                    _state.update { it.copy(loading = false, error = outcome.message) }
            }
        }
    }

    fun logout() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            withContext(workDispatcher) { repo.logout() }
            _state.update { it.copy(loading = false, status = AuthStatus.SignedOut) }
        }
    }
}
