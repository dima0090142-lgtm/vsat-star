package com.vsatstar.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.CookieManager
import java.net.CookiePolicy
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URI
import java.net.URL
import java.net.URLEncoder

class PanelException(message: String) : Exception(message)

/**
 * Запросы к панели судна - перенос terminal_switch.py: вход, переключение терминала,
 * logout и трафик.
 *
 * Запросы идут именно через Wi-Fi: если у Wi-Fi судна ещё нет интернета, Android
 * сам уводит обычные запросы в мобильную сеть, и панель оказывается недоступна.
 */
object Panel {
    private const val USER_AGENT =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

    /** Точное написание, как ожидает сервер. */
    fun terminalValue(state: ConnState) = when (state) {
        ConnState.STARLINK -> "Starlink"
        ConnState.VSAT -> "VSAT"
        else -> throw IllegalArgumentException("Не терминал: $state")
    }

    // Сессия панели живёт, пока жив процесс приложения
    private val cookies = CookieManager(null, CookiePolicy.ACCEPT_ALL)

    private val base get() = "http://${Prefs.host}"
    private val loginUrl get() = "$base/index.php/login"
    private val switchUrl get() = "$base/index.php/crew/start_internet"
    private val logoutUrl get() = "$base/index.php/chilli_logout"
    private val usageUrl get() = "$base/index.php/card-usage"

    private class Response(val code: Int, val body: String)

    suspend fun login(context: Context, username: String, password: String) {
        // Новый вход - старые куки больше не нужны
        cookies.cookieStore.removeAll()
        request(context, "GET", loginUrl, timeoutMs = 10_000)
        val form = "username=${enc(username)}&password=${enc(password)}"
        val resp = request(
            context, "POST", loginUrl,
            headers = mapOf(
                "Content-Type" to "application/x-www-form-urlencoded",
                "Origin" to base,
                "Referer" to loginUrl,
            ),
            body = form, timeoutMs = 10_000,
        )
        if (resp.code != 200) throw PanelException("Ошибка авторизации (код ${resp.code}) - проверьте логин и пароль")
    }

    suspend fun switchTerminal(context: Context, terminal: ConnState): String {
        val value = terminalValue(terminal)
        // Тело формально JSON, хотя Content-Type - urlencoded: так делает сам сайт
        val resp = request(
            context, "POST", switchUrl,
            headers = mapOf(
                "Accept" to "application/json, text/javascript, */*; q=0.01",
                "Content-Type" to "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin" to base,
                "Referer" to "$base/index.php",
                "X-Requested-With" to "XMLHttpRequest",
            ),
            body = "{\"terminal\":\"$value\"}", timeoutMs = 15_000,
        )
        if (resp.code != 200) throw PanelException("Панель вернула код ${resp.code} при переключении на $value")
        return resp.body
    }

    suspend fun logout(context: Context) {
        val resp = request(context, "GET", logoutUrl, headers = mapOf("Referer" to "$base/index.php"), timeoutMs = 10_000)
        if (resp.code != 200) throw PanelException("Панель вернула код ${resp.code} при отключении")
    }

    /** Один запрос страницы трафика, без повторного входа (чтобы не сбросить подключение). */
    suspend fun usage(context: Context): Usage {
        val resp = request(context, "GET", usageUrl, timeoutMs = 10_000)
        return withContext(Dispatchers.Default) { UsageParser.parse(resp.body) }
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    private fun wifiNetwork(context: Context): Network? {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return null
        @Suppress("DEPRECATION")
        return cm.allNetworks.firstOrNull {
            cm.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        }
    }

    private suspend fun request(
        context: Context,
        method: String,
        url: String,
        headers: Map<String, String> = emptyMap(),
        body: String? = null,
        timeoutMs: Int,
    ): Response = withContext(Dispatchers.IO) {
        val network = wifiNetwork(context)
        var currentUrl = url
        var currentMethod = method
        var currentBody = body
        try {
            // Редиректы обрабатываем сами: так каждый шаг идёт через Wi-Fi и с нашими куками
            repeat(MAX_REDIRECTS) {
                val conn = open(network, currentUrl)
                try {
                    conn.instanceFollowRedirects = false
                    conn.connectTimeout = timeoutMs
                    conn.readTimeout = timeoutMs
                    conn.requestMethod = currentMethod
                    conn.setRequestProperty("User-Agent", USER_AGENT)
                    conn.setRequestProperty("Accept-Language", "ru,en;q=0.9")
                    headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }
                    val uri = URI(currentUrl)
                    cookies.get(uri, emptyMap()).forEach { (k, values) ->
                        if (values.isNotEmpty()) conn.setRequestProperty(k, values.joinToString("; "))
                    }
                    if (currentBody != null) {
                        conn.doOutput = true
                        conn.outputStream.use { it.write(currentBody!!.toByteArray(Charsets.UTF_8)) }
                    }
                    val code = conn.responseCode
                    cookies.put(uri, conn.headerFields.filterKeys { it != null })
                    val location = conn.getHeaderField("Location")
                    if (code in 300..399 && location != null) {
                        currentUrl = URL(URL(currentUrl), location).toString()
                        if (code != 307 && code != 308) {
                            currentMethod = "GET"
                            currentBody = null
                        }
                        return@repeat
                    }
                    val stream = if (code >= 400) conn.errorStream else conn.inputStream
                    val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
                    return@withContext Response(code, text)
                } finally {
                    conn.disconnect()
                }
            }
            throw PanelException("Слишком много перенаправлений от панели")
        } catch (e: SocketTimeoutException) {
            throw PanelException("Панель не отвечает (тайм-аут)")
        } catch (e: IOException) {
            throw PanelException(
                if (network == null) "Нет Wi-Fi - подключитесь к Wi-Fi судна"
                else "Нет связи с панелью ${Prefs.host}"
            )
        }
    }

    private fun open(network: Network?, url: String): HttpURLConnection =
        (network?.openConnection(URL(url)) ?: URL(url).openConnection()) as HttpURLConnection

    private const val MAX_REDIRECTS = 6
}
