package org.hitchwiki.maps.data

/** Secure local storage for the bearer token. Android impl uses EncryptedSharedPreferences;
 *  tests use an in-memory fake. */
interface TokenStore {
    suspend fun save(token: String)
    suspend fun load(): String?
    suspend fun clear()
}
