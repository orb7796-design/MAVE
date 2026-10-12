package com.mave.app.data

import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import retrofit2.Call
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Holds the tokens in memory; persisted separately in encrypted storage.
 * [onTokens] is called (from a network thread) after a silent refresh so the new pair can be saved.
 * [onExpired] is called when the server definitively rejected the session (user must log in again).
 */
object Session {
    @Volatile
    var token: String? = null

    @Volatile
    var refreshToken: String? = null

    @Volatile
    var onTokens: ((String, String?) -> Unit)? = null

    @Volatile
    var onExpired: (() -> Unit)? = null
}

interface MaveApi {
    @GET("search")
    suspend fun search(@Query("q") q: String, @Query("type") type: String, @Query("page") page: Int, @Query("lang") lang: String? = null): SearchResponse

    @GET("suggest")
    suspend fun suggest(@Query("q") q: String): SuggestResponse

    @GET("trending")
    suspend fun trending(): TrendingResponse

    @POST("ai/answer")
    suspend fun answer(@Body req: AiRequest): AiAnswer

    @POST("auth/login")
    suspend fun login(@Body req: AuthRequest): AuthResponse

    @POST("auth/register")
    suspend fun register(@Body req: AuthRequest): AuthResponse

    @POST("auth/logout")
    suspend fun logout(@Body req: LogoutRequest): Ok

    @POST("auth/forgot-password")
    suspend fun forgotPassword(@Body req: ForgotRequest): Ok

    @POST("auth/reset-password")
    suspend fun resetPassword(@Body req: ResetRequest): Ok

    @GET("me/history")
    suspend fun history(): HistoryResponse

    @POST("me/history")
    suspend fun addHistory(@Body body: HistoryAdd): Ok

    @DELETE("me/history")
    suspend fun deleteHistory(@Query("q") q: String?): Ok

    @GET("me/saved")
    suspend fun saved(): SavedResponse

    @POST("me/saved")
    suspend fun addSaved(@Body item: SearchItem): Ok

    @DELETE("me/saved")
    suspend fun deleteSaved(@Query("url") url: String): Ok
}

/** Blocking variant used only by the OkHttp [Authenticator], which runs on a network thread. */
internal interface RefreshApi {
    @POST("auth/refresh")
    fun refresh(@Body req: RefreshRequest): Call<AuthResponse>
}

object Network {
    @Volatile
    private var baseUrl: String? = null

    /**
     * Must be called once, before the first request (the app does it in `MaveApplication.onCreate`).
     * [url] is the server root ending in "/" (e.g. `https://api.example.org/`); the versioned `api/v1/` path is added here.
     */
    fun configure(url: String) {
        require(url.endsWith("/")) { "Base URL must end with '/': $url" }
        baseUrl = url
    }

    /** Endpoints that must never carry a (possibly stale) bearer token. */
    private val noBearer = listOf("auth/login", "auth/register", "auth/refresh", "auth/forgot-password", "auth/reset-password")

    private val refreshLock = Any()

    private val authInterceptor = Interceptor { chain ->
        val token = Session.token
        val path = chain.request().url.encodedPath
        val req = if (token != null && noBearer.none { path.endsWith(it) }) {
            chain.request().newBuilder().header("Authorization", "Bearer $token").build()
        } else chain.request()
        chain.proceed(req)
    }

    /** On 401 for a request that carried our token: refresh once (serialised), then retry that request. */
    private val authenticator = Authenticator { _, response -> reauthenticate(response) }

    private val client = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .authenticator(authenticator)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .build()

    // No interceptor/authenticator here: the refresh call must not recurse into itself.
    private val bareClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    // Versioned API; the server also keeps the legacy root paths for old clients.
    private fun retrofit(c: OkHttpClient): Retrofit = Retrofit.Builder()
        .baseUrl(checkNotNull(baseUrl) { "Network.configure(...) must be called before the first request" } + "api/v1/")
        .client(c)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    val api: MaveApi by lazy { retrofit(client).create(MaveApi::class.java) }

    private val refreshApi: RefreshApi by lazy { retrofit(bareClient).create(RefreshApi::class.java) }

    private fun reauthenticate(response: Response): Request? {
        val sent = response.request.header("Authorization") ?: return null // login/register/... carry no token
        if (response.priorResponse != null) return null // already retried once: give up, never loop
        val sentToken = sent.removePrefix("Bearer ").trim()
        return synchronized(refreshLock) { refreshLocked(response, sentToken) }
    }

    private fun retryWith(response: Response, token: String): Request =
        response.request.newBuilder().header("Authorization", "Bearer $token").build()

    private fun refreshLocked(response: Response, sentToken: String): Request? {
        val current = Session.token
        // Another request refreshed while this one waited for the lock: just retry with the new token.
        if (current != null && current != sentToken) return retryWith(response, current)

        val refresh = Session.refreshToken
        if (refresh == null) {
            Session.onExpired?.invoke()
            return null
        }
        return try {
            val r = refreshApi.refresh(RefreshRequest(refresh)).execute()
            val body = r.body()
            when {
                r.isSuccessful && body != null -> {
                    val newRefresh = body.refreshToken ?: refresh
                    Session.token = body.token
                    Session.refreshToken = newRefresh
                    Session.onTokens?.invoke(body.token, newRefresh)
                    retryWith(response, body.token)
                }
                // The server rejected this refresh token (revoked, expired, replayed): the session is over.
                r.code() in 400..403 || r.code() == 422 -> {
                    Session.onExpired?.invoke()
                    null
                }
                else -> null // 429 / 5xx: keep the session, fail only this request
            }
        } catch (e: IOException) {
            null // offline: keep the session so the user is not logged out by a bad connection
        }
    }
}
