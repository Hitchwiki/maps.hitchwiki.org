package org.hitchwiki.maps.model
import kotlinx.serialization.Serializable

@Serializable
data class TokenRequest(val code: String)

@Serializable
data class TokenResponse(val token: String, val username: String)

@Serializable
data class MeResponse(val username: String)
