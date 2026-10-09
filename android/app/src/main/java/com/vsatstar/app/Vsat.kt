package com.vsatstar.app

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import android.os.SystemClock
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

enum class Action(val busyText: String) {
    STARLINK("Переключаю на Starlink…"),
    VSAT("Переключаю на VSAT…"),
    DISCONNECT("Отключаю…"),
    USAGE("Запрашиваю трафик…"),
}

data class UiState(
    val conn: ConnState = ConnState.UNKNOWN,
    /** Текст выполняемого действия или null. */
    val busy: String? = null,
    val detail: String = "",
    val isError: Boolean = false,
    val usage: Usage? = null,
    val usageCaption: String = "",
    /** SystemClock.elapsedRealtime последнего удачного запроса трафика, 0 - не было. */
    val usageAt: Long = 0L,
    /** Остаток времени меньше порога напоминания. */
    val lowTime: Boolean = false,
)

/** Все действия приложения. Живёт вместе с процессом, общий для экрана и шторки. */
object Vsat {
    const val USAGE_REFRESH_MS = 10L * 60 * 1000
    const val REMIND_MINUTES = 30

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    private lateinit var app: Context
    private var job: Job? = null
    private var limitReminded = false

    val isBusy get() = job?.isActive == true

    fun init(context: Context) {
        app = context.applicationContext
        val conn = Prefs.connState
        _state.value = UiState(conn = conn, detail = sinceText(conn, Prefs.stateSince))
    }

    /**
     * Запускает действие. [quiet] - фоновое обновление: не показывает "занято" и не
     * выводит ошибки крупно. [auto] - отключение по таймеру простоя.
     */
    fun perform(action: Action, quiet: Boolean = false, auto: Boolean = false): Boolean {
        if (isBusy) return false
        if (action != Action.USAGE && !Prefs.hasCredentials) {
            _state.update { it.copy(detail = "Введите логин и пароль в настройках", isError = true) }
            return false
        }
        job = scope.launch { execute(action, quiet, auto) }
        return true
    }

    private suspend fun execute(action: Action, quiet: Boolean, auto: Boolean) {
        if (!quiet) _state.update { it.copy(busy = action.busyText) }
        try {
            when (action) {
                Action.USAGE -> onUsage(Panel.usage(app))
                Action.DISCONNECT -> {
                    Panel.login(app, Prefs.username, Prefs.password)
                    Panel.logout(app)
                    setConn(ConnState.DISCONNECTED)
                    if (auto) Notifier.showAutoOff(app)
                }
                Action.STARLINK, Action.VSAT -> {
                    val terminal = if (action == Action.STARLINK) ConnState.STARLINK else ConnState.VSAT
                    Panel.login(app, Prefs.username, Prefs.password)
                    Panel.switchTerminal(app, terminal)
                    setConn(terminal)
                    limitReminded = false
                    // Сразу узнаём остаток времени
                    scope.launch {
                        delay(3000)
                        perform(Action.USAGE, quiet = true)
                    }
                }
            }
        } catch (e: PanelException) {
            val message = e.message ?: "Ошибка"
            when {
                quiet || auto -> _state.update { it.copy(usageCaption = "ошибка в ${hm()}") }
                action == Action.USAGE -> _state.update { it.copy(usageCaption = "ошибка запроса", detail = "Трафик не получен: $message", isError = true) }
                else -> _state.update { it.copy(detail = message, isError = true) }
            }
        } finally {
            _state.update { it.copy(busy = null) }
        }
    }

    private fun setConn(conn: ConnState) {
        val now = System.currentTimeMillis()
        Prefs.connState = conn
        Prefs.stateSince = now
        // Цифры трафика относились к прошлому подключению
        _state.update {
            it.copy(
                conn = conn, detail = sinceText(conn, now), isError = false,
                usage = null, usageCaption = "", usageAt = 0L, lowTime = false,
            )
        }
    }

    private fun onUsage(usage: Usage) {
        val now = SystemClock.elapsedRealtime()
        if (usage.isEmpty) {
            _state.update { it.copy(usage = null, usageCaption = "нет данных", usageAt = now) }
            return
        }
        val minutes = UsageParser.remainingMinutes(usage.remainingTime)
        val low = minutes != null && minutes <= REMIND_MINUTES
        _state.update {
            val detail = if (it.isError) sinceText(it.conn, Prefs.stateSince) else it.detail
            it.copy(usage = usage, usageCaption = "обновлено в ${hm()}", usageAt = now, lowTime = low, detail = detail, isError = false)
        }
        if (!low) {
            limitReminded = false
        } else if (!limitReminded) {
            limitReminded = true
            if (Prefs.limitReminder) {
                Notifier.showLimitReminder(app, "До конца дневного лимита осталось ${minutes!!.toInt().coerceAtLeast(0)} мин")
            }
        }
    }

    /** Только для скриншот-тестов: подставить состояние экрана. */
    internal fun previewState(state: UiState) {
        _state.value = state
    }

    fun clearError() {
        _state.update { if (it.isError) it.copy(isError = false, detail = sinceText(it.conn, Prefs.stateSince)) else it }
    }

    private fun sinceText(conn: ConnState, since: Long): String {
        if (since <= 0) return ""
        val time = SimpleDateFormat("dd.MM HH:mm", Locale.getDefault()).format(Date(since))
        return when (conn) {
            ConnState.STARLINK, ConnState.VSAT -> "Подключено $time"
            ConnState.DISCONNECTED -> "Отключено $time"
            ConnState.UNKNOWN -> ""
        }
    }

    private fun hm() = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
}

val ConnState.isConnected get() = this == ConnState.STARLINK || this == ConnState.VSAT

val ConnState.label
    get() = when (this) {
        ConnState.STARLINK -> "Starlink"
        ConnState.VSAT -> "VSAT"
        ConnState.DISCONNECTED -> "Отключено"
        ConnState.UNKNOWN -> "Не подключено"
    }
