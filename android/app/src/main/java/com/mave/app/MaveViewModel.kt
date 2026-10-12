package com.mave.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mave.app.data.AiAnswer
import com.mave.app.data.AiRequest
import com.mave.app.data.AuthRequest
import com.mave.app.data.ForgotRequest
import com.mave.app.data.HistoryAdd
import com.mave.app.data.LocalStore
import com.mave.app.data.LogoutRequest
import com.mave.app.data.Network
import com.mave.app.data.Persisted
import com.mave.app.data.ResetRequest
import com.mave.app.data.SearchItem
import com.mave.app.data.SecureStore
import com.mave.app.data.Session
import com.mave.app.ui.L
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/** State of the "load more" footer of a result list. */
enum class Paging { IDLE, LOADING, ERROR, END }

/** The server accepts page 1..20 (`le=20`); asking for more would only give a 422. */
private const val MAX_PAGE = 20

class MaveViewModel(app: Application) : AndroidViewModel(app) {
    private val store = LocalStore(app)
    private val secure = SecureStore(app)

    // App state (persisted)
    var loaded by mutableStateOf(false); private set
    var onboarded by mutableStateOf(false); private set
    var darkMode by mutableStateOf(false); private set
    var lang by mutableStateOf("om"); private set // "om" = Afaan Oromoo, "en" = English
    var user by mutableStateOf<String?>(null); private set
    val saved = mutableStateListOf<SearchItem>()
    val history = mutableStateListOf<String>()

    // Auth UI
    var authError by mutableStateOf<String?>(null); private set
    var resetInfo by mutableStateOf<String?>(null); private set // error text of the reset-password dialog

    // Search state
    var query by mutableStateOf(""); private set
    var pending by mutableStateOf(0); private set
    val loading: Boolean get() = pending > 0
    var error by mutableStateOf<String?>(null); private set
    var aiAnswer by mutableStateOf<AiAnswer?>(null); private set
    var didYouMean by mutableStateOf<String?>(null); private set
    val results = mutableStateMapOf<String, List<SearchItem>>()
    private val inFlight = mutableSetOf<String>()

    // Pagination (per tab): next page to request, and the state of the "load more" footer.
    // `generation` changes with every new search so a late response of an old search is never shown.
    private val nextPage = mutableMapOf<String, Int>()
    private val paging = mutableStateMapOf<String, Paging>()
    private var generation = 0

    var trending by mutableStateOf(listOf("Artificial Intelligence", "Afaan Oromoo", "Technology news", "Startups", "Kotlin"))
        private set
    var suggestions by mutableStateOf<List<String>>(emptyList()); private set
    private var suggestJob: Job? = null

    init {
        // A silent token refresh happens on a network thread: persist the new pair, or sign out if the server ended the session.
        Session.onTokens = { access, refresh ->
            secure.token = access
            secure.refreshToken = refresh
        }
        Session.onExpired = { viewModelScope.launch { logout(notifyServer = false) } }
        viewModelScope.launch {
            val p = store.read()
            darkMode = p.dark ?: false
            lang = p.lang ?: "om"
            onboarded = p.onboarded ?: false
            saved.addAll(p.saved.orEmpty())
            history.addAll(p.history.orEmpty())
            val token = secure.token
            if (token != null && p.user != null) {
                Session.token = token
                Session.refreshToken = secure.refreshToken
                user = p.user
            }
            loaded = true
            bg { trending = Network.api.trending().trending.ifEmpty { trending } }
            if (user != null) syncWithServer()
        }
    }

    // ---------------- helpers
    private fun persist() {
        val snap = Persisted(darkMode, lang, onboarded, user, saved.toList(), history.toList())
        viewModelScope.launch { store.write(snap) }
    }

    /** Fire-and-forget network work. Offline failures are fine: the local copy is the source of truth. */
    private fun bg(block: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: HttpException) {
                // 401 is handled by Network's Authenticator (silent refresh, or Session.onExpired -> logout)
            } catch (e: Exception) {
                // ignore
            }
        }
    }

    private fun friendly(e: Exception): String = when {
        e is IOException -> L.t("err_network", lang)
        e is HttpException && e.code() == 429 -> L.t("err_rate", lang)
        e is HttpException && e.code() == 502 -> L.t("err_provider", lang)
        else -> L.t("err_server", lang)
    }

    // ---------------- settings
    fun setDark(v: Boolean) { darkMode = v; persist() }
    fun updateLang(v: String) { lang = v; persist() }
    fun markOnboarded() { onboarded = true; persist() }

    // ---------------- search
    fun onTyping(text: String) {
        suggestJob?.cancel()
        if (text.isBlank()) { suggestions = emptyList(); return }
        suggestJob = viewModelScope.launch {
            delay(250)
            suggestions = try {
                Network.api.suggest(text.trim()).suggestions
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                emptyList()
            }
        }
    }

    fun clearSuggestions() { suggestJob?.cancel(); suggestions = emptyList() }

    fun runSearch(q: String) {
        val clean = q.trim()
        if (clean.isEmpty()) return
        clearSuggestions()
        history.remove(clean)
        history.add(0, clean)
        while (history.size > 100) history.removeAt(history.lastIndex)
        persist()
        if (Session.token != null) bg { Network.api.addHistory(HistoryAdd(clean)) }
        if (clean == query && (results.isNotEmpty() || aiAnswer != null)) return
        query = clean
        generation++
        results.clear()
        nextPage.clear()
        paging.clear()
        aiAnswer = null
        didYouMean = null
        error = null
        inFlight.clear()
    }

    fun loadTab(tab: String) {
        val q = query
        if (q.isEmpty()) return
        val already = if (tab == "ai") aiAnswer != null else results.containsKey(tab)
        if (already || !inFlight.add(tab)) return
        val gen = generation
        viewModelScope.launch {
            pending++
            try {
                if (tab == "ai") {
                    val answer = Network.api.answer(AiRequest(q, lang))
                    if (gen != generation) return@launch // a newer search replaced this one
                    aiAnswer = answer
                } else {
                    val resp = Network.api.search(q, tab, 1, lang)
                    if (gen != generation) return@launch
                    results[tab] = resp.results
                    nextPage[tab] = 2
                    paging[tab] = if (resp.results.isEmpty()) Paging.END else Paging.IDLE
                    if (tab == "web") didYouMean = resp.corrected
                }
                error = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (gen == generation) error = friendly(e)
            } finally {
                if (gen == generation) inFlight.remove(tab)
                pending--
            }
        }
    }

    fun pagingOf(tab: String): Paging = paging[tab] ?: Paging.IDLE

    /** Infinite scroll: fetch the next page of [tab] and append it (duplicates by URL are dropped). */
    fun loadMore(tab: String) {
        val q = query
        if (q.isEmpty() || tab == "ai") return
        if (!results.containsKey(tab)) return // first page not loaded yet
        if (pagingOf(tab) != Paging.IDLE) return // already loading, failed (user must tap retry) or finished
        if (inFlight.contains(tab)) return
        val page = nextPage[tab] ?: return
        if (page > MAX_PAGE) { paging[tab] = Paging.END; return }
        val gen = generation
        inFlight.add(tab)
        paging[tab] = Paging.LOADING
        viewModelScope.launch {
            try {
                val resp = Network.api.search(q, tab, page, lang)
                if (gen != generation) return@launch
                val known = results[tab].orEmpty()
                // Image results often share one page URL, so images are told apart by their thumbnail.
                val idOf = { item: SearchItem -> if (tab == "images") (item.thumbnail ?: item.url) else item.url }
                val seen = known.mapTo(HashSet()) { idOf(it) }
                val fresh = resp.results.filter { seen.add(idOf(it)) }
                if (fresh.isNotEmpty()) results[tab] = known + fresh
                nextPage[tab] = page + 1
                paging[tab] = if (resp.results.isEmpty() || page >= MAX_PAGE) Paging.END else Paging.IDLE
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Keep what is already on screen; only the footer shows an error + retry.
                if (gen == generation) paging[tab] = Paging.ERROR
            } finally {
                if (gen == generation) inFlight.remove(tab)
            }
        }
    }

    fun retryMore(tab: String) {
        if (pagingOf(tab) == Paging.ERROR) {
            paging[tab] = Paging.IDLE
            loadMore(tab)
        }
    }

    fun retry(tab: String) { error = null; loadTab(tab) }

    // ---------------- library
    fun isSaved(item: SearchItem) = saved.any { it.url == item.url }

    fun toggleSave(item: SearchItem) {
        val idx = saved.indexOfFirst { it.url == item.url }
        if (idx >= 0) {
            saved.removeAt(idx)
            if (Session.token != null) bg { Network.api.deleteSaved(item.url) }
        } else {
            saved.add(0, item)
            if (Session.token != null) bg { Network.api.addSaved(item) }
        }
        persist()
    }

    fun clearHistory() {
        history.clear(); persist()
        if (Session.token != null) bg { Network.api.deleteHistory(null) }
    }

    fun removeHistory(q: String) {
        history.remove(q); persist()
        if (Session.token != null) bg { Network.api.deleteHistory(q) }
    }

    // ---------------- auth
    fun authenticate(email: String, password: String, register: Boolean, onOk: () -> Unit) {
        val e = email.trim()
        if (!e.contains("@") || e.length < 5) { authError = L.t("err_email", lang); return }
        if (password.length < 8) { authError = L.t("err_pw_short", lang); return }
        viewModelScope.launch {
            try {
                val req = AuthRequest(e, password)
                val r = if (register) Network.api.register(req) else Network.api.login(req)
                Session.token = r.token
                Session.refreshToken = r.refreshToken
                secure.token = r.token
                secure.refreshToken = r.refreshToken
                user = r.email
                authError = null
                persist()
                onOk()
                syncWithServer()
            } catch (ex: CancellationException) {
                throw ex
            } catch (ex: HttpException) {
                authError = when (ex.code()) {
                    401 -> L.t("err_login", lang)
                    409 -> L.t("err_exists", lang)
                    else -> friendly(ex)
                }
            } catch (ex: Exception) {
                authError = friendly(ex)
            }
        }
    }

    fun logout(notifyServer: Boolean = true) {
        val refresh = Session.refreshToken
        Session.token = null
        Session.refreshToken = null
        secure.token = null
        secure.refreshToken = null
        user = null
        persist()
        if (notifyServer && refresh != null) {
            // Best effort: if we are offline the server session simply expires on its own.
            viewModelScope.launch {
                try {
                    Network.api.logout(LogoutRequest(refresh))
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    // ignore
                }
            }
        }
    }

    // ---------------- password reset (code arrives by e-mail)
    fun clearResetInfo() { resetInfo = null }

    fun requestReset(email: String, onSent: () -> Unit) {
        val e = email.trim()
        if (!e.contains("@") || e.length < 5) { resetInfo = L.t("err_email", lang); return }
        viewModelScope.launch {
            try {
                Network.api.forgotPassword(ForgotRequest(e))
                resetInfo = null
                onSent()
            } catch (ex: CancellationException) {
                throw ex
            } catch (ex: Exception) {
                resetInfo = friendly(ex)
            }
        }
    }

    fun completeReset(code: String, password: String, onDone: () -> Unit) {
        val c = code.trim()
        if (c.length < 10) { resetInfo = L.t("err_code", lang); return }
        if (password.length < 8) { resetInfo = L.t("err_pw_short", lang); return }
        viewModelScope.launch {
            try {
                Network.api.resetPassword(ResetRequest(c, password))
                resetInfo = null
                onDone()
            } catch (ex: CancellationException) {
                throw ex
            } catch (ex: HttpException) {
                resetInfo = if (ex.code() == 400 || ex.code() == 422) L.t("err_code_invalid", lang) else friendly(ex)
            } catch (ex: Exception) {
                resetInfo = friendly(ex)
            }
        }
    }

    /** Merge server and local data (union), then push local-only items up. */
    private fun syncWithServer() = bg {
        val remoteSaved = Network.api.saved().items
        val remoteHistory = Network.api.history().items
        val localOnlySaved = saved.filter { s -> remoteSaved.none { it.url == s.url } }
        val localOnlyHistory = history.filter { it !in remoteHistory }
        saved.clear(); saved.addAll(localOnlySaved + remoteSaved)
        history.clear(); history.addAll((localOnlyHistory + remoteHistory).distinct().take(100))
        persist()
        localOnlySaved.forEach { Network.api.addSaved(it) }
        localOnlyHistory.reversed().forEach { Network.api.addHistory(HistoryAdd(it)) }
    }
}
