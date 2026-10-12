package com.mave.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson
import kotlinx.coroutines.flow.first

private val Context.dataStore by preferencesDataStore(name = "mave")

/** Everything except the auth token. All fields nullable so older/newer saved states never crash. */
data class Persisted(
    val dark: Boolean? = null,
    val lang: String? = null,
    val onboarded: Boolean? = null,
    val user: String? = null,
    val saved: List<SearchItem>? = null,
    val history: List<String>? = null
)

class LocalStore(private val ctx: Context) {
    private val gson = Gson()
    private val key = stringPreferencesKey("state")

    suspend fun read(): Persisted = try {
        ctx.dataStore.data.first()[key]?.let { gson.fromJson(it, Persisted::class.java) } ?: Persisted()
    } catch (e: Exception) {
        Persisted()
    }

    suspend fun write(p: Persisted) {
        ctx.dataStore.edit { it[key] = gson.toJson(p) }
    }
}

/** Access + refresh token live in EncryptedSharedPreferences (Android Keystore). Falls back to memory-only if unavailable. */
class SecureStore(ctx: Context) {
    private val prefs = runCatching {
        EncryptedSharedPreferences.create(
            ctx,
            "mave_secure",
            MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }.getOrNull()

    private var memory: String? = null
    private var memoryRefresh: String? = null

    var token: String?
        get() = prefs?.getString("token", null) ?: memory
        set(value) {
            memory = value
            prefs?.edit()?.apply {
                if (value == null) remove("token") else putString("token", value)
            }?.apply()
        }

    var refreshToken: String?
        get() = prefs?.getString("refresh_token", null) ?: memoryRefresh
        set(value) {
            memoryRefresh = value
            prefs?.edit()?.apply {
                if (value == null) remove("refresh_token") else putString("refresh_token", value)
            }?.apply()
        }
}
