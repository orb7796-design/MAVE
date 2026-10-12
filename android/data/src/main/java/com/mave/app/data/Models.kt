package com.mave.app.data

import com.google.gson.annotations.SerializedName

data class SearchItem(
    val title: String,
    val url: String,
    val snippet: String,
    val thumbnail: String?
)

data class SearchResponse(val results: List<SearchItem>, val corrected: String? = null, val page: Int? = null)

data class SuggestResponse(val suggestions: List<String>)

data class TrendingResponse(val trending: List<String>)

data class HistoryResponse(val items: List<String>)

data class SavedResponse(val items: List<SearchItem>)

data class HistoryAdd(val query: String)

data class Ok(val ok: Boolean)

data class AiRequest(val query: String, val lang: String)

data class Citation(val n: Int, val title: String, val url: String)

// Phase 5 fields are nullable: Gson leaves missing fields null (older servers do not send them).
data class AiAnswer(
    val answer: String,
    val sources: List<SearchItem>,
    val citations: List<Citation>? = null,
    val grounded: Boolean? = null,
    val insufficient: Boolean? = null
)

data class AuthRequest(val email: String, val password: String)

data class AuthResponse(
    val token: String,
    val email: String,
    // Nullable with defaults: Gson fills missing fields with null, and older servers do not send them.
    @SerializedName("refresh_token") val refreshToken: String? = null,
    @SerializedName("expires_in") val expiresIn: Long? = null,
    @SerializedName("email_verified") val emailVerified: Boolean? = null
)

data class RefreshRequest(@SerializedName("refresh_token") val refreshToken: String)

data class LogoutRequest(@SerializedName("refresh_token") val refreshToken: String?)

data class ForgotRequest(val email: String)

data class ResetRequest(val token: String, val password: String)
