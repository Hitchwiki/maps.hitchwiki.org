package org.hitchwiki.maps.data
import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** TokenStore backed by EncryptedSharedPreferences (AES via the Android Keystore). */
class EncryptedTokenStore(context: Context) : TokenStore {
    private val prefs by lazy {
        val key = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "hitchwiki_auth",
            key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    override suspend fun save(token: String) = withContext(Dispatchers.IO) {
        prefs.edit().putString(KEY, token).apply()
    }

    override suspend fun load(): String? = withContext(Dispatchers.IO) {
        prefs.getString(KEY, null)
    }

    override suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit().remove(KEY).apply()
    }

    private companion object { const val KEY = "bearer_token" }
}
