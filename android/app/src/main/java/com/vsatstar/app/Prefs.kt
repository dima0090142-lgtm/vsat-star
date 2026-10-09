package com.vsatstar.app

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/** Активный терминал. Панель его не сообщает, поэтому запоминаем последнее успешное действие. */
enum class ConnState { STARLINK, VSAT, DISCONNECTED, UNKNOWN }

/**
 * Локальные настройки. Логин и пароль хранятся только в приватном хранилище приложения
 * на телефоне - как и в Windows-версии, никуда не отправляются, кроме панели судна.
 */
object Prefs {
    const val DEFAULT_HOST = "192.168.50.2"

    private lateinit var sp: SharedPreferences

    fun init(context: Context) {
        sp = context.getSharedPreferences("vsat_star", Context.MODE_PRIVATE)
    }

    var username: String
        get() = sp.getString("username", "") ?: ""
        set(value) = sp.edit { putString("username", value) }

    var password: String
        get() = sp.getString("password", "") ?: ""
        set(value) = sp.edit { putString("password", value) }

    var host: String
        get() = sp.getString("host", null)?.takeIf { it.isNotBlank() } ?: DEFAULT_HOST
        set(value) = sp.edit { putString("host", value.trim()) }

    val hasCredentials: Boolean
        get() = username.isNotBlank() && password.isNotEmpty()

    var connState: ConnState
        get() = runCatching { ConnState.valueOf(sp.getString("conn_state", null) ?: "") }
            .getOrDefault(ConnState.UNKNOWN)
        set(value) = sp.edit { putString("conn_state", value.name) }

    /** Время (System.currentTimeMillis) последнего подключения/отключения. */
    var stateSince: Long
        get() = sp.getLong("state_since", 0L)
        set(value) = sp.edit { putLong("state_since", value) }

    /** Значок текущего подключения в шторке. */
    var showStatusIcon: Boolean
        get() = sp.getBoolean("show_status_icon", true)
        set(value) = sp.edit { putBoolean("show_status_icon", value) }

    /** Напоминание за 30 минут до конца дневного лимита. */
    var limitReminder: Boolean
        get() = sp.getBoolean("limit_reminder", true)
        set(value) = sp.edit { putBoolean("limit_reminder", value) }

    /** Экспериментально: отключать интернет, если час нет трафика. */
    var autoOff: Boolean
        get() = sp.getBoolean("auto_off", false)
        set(value) = sp.edit { putBoolean("auto_off", value) }

    /** Нужен ли фоновый сервис (значок в шторке или автоотключение). */
    val serviceNeeded: Boolean
        get() = showStatusIcon || autoOff
}
