package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.data.AuthStatus

data class AccountUiState(
    val loading: Boolean = false,
    val status: AuthStatus = AuthStatus.Unknown,
    val error: String? = null,
)
