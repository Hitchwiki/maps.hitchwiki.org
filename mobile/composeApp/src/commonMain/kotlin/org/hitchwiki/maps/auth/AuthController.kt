package org.hitchwiki.maps.auth

/** Drives the system-browser OAuth leg and returns the one-time code (or cancel/error).
 *  Android impl opens a Custom Tab and awaits the custom-scheme redirect. */
interface AuthController {
    suspend fun signIn(): AuthResult
}

sealed interface AuthResult {
    data class Success(val code: String) : AuthResult
    data object Cancelled : AuthResult
    data class Error(val message: String) : AuthResult
}
