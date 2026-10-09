package com.vsatstar.app

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.TrafficStats
import android.os.Build
import android.os.IBinder
import android.os.Process
import android.os.SystemClock
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Держит значок текущего подключения в шторке, раз в 10 минут обновляет трафик и
 * (экспериментально) отключает интернет, если час не было трафика.
 */
class StatusService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var started = false

    private val idle = IdleWatcher(now = SystemClock::elapsedRealtime, bytes = ::wifiBytes)
    private var lastConn: ConnState? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // startForeground нужно вызвать сразу при каждом старте
        ServiceCompat.startForeground(
            this, Notifier.STATUS_ID,
            Notifier.buildStatus(this, Vsat.state.value, null),
            if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0,
        )

        intent?.getStringExtra(EXTRA_ACTION)?.let { name ->
            runCatching { Action.valueOf(name) }.getOrNull()?.let { Vsat.perform(it) }
        }

        if (!Prefs.serviceNeeded) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!started) {
            started = true
            scope.launch { Vsat.state.collect { onState(it) } }
            scope.launch { tickLoop() }
        }
        return START_STICKY
    }

    private fun onState(state: UiState) {
        if (state.conn != lastConn) {
            lastConn = state.conn
            idle.reset()
        }
        refreshNotification(state)
    }

    private fun refreshNotification(state: UiState = Vsat.state.value) {
        val idleMin = if (Prefs.autoOff && state.conn.isConnected) idle.idleMs() / 60_000 else null
        try {
            NotificationManagerCompat.from(this).notify(Notifier.STATUS_ID, Notifier.buildStatus(this, state, idleMin))
        } catch (_: SecurityException) {
            // Нет разрешения на уведомления - сервис работает и без значка
        }
    }

    private suspend fun tickLoop() {
        while (scope.isActive) {
            delay(TICK_MS)
            val state = Vsat.state.value
            if (!state.conn.isConnected || Vsat.isBusy) continue

            if (Prefs.autoOff) {
                if (idle.tick()) {
                    Vsat.perform(Action.DISCONNECT, quiet = true, auto = true)
                    continue
                }
            } else {
                idle.reset()
            }

            val now = SystemClock.elapsedRealtime()
            if (state.usageAt == 0L || now - state.usageAt >= Vsat.USAGE_REFRESH_MS) {
                Vsat.perform(Action.USAGE, quiet = true)
            }
            refreshNotification()
        }
    }

    /** Трафик не через мобильную сеть (то есть Wi-Fi судна) без учёта самого приложения. */
    private fun wifiBytes(): Long {
        val total = TrafficStats.getTotalRxBytes() + TrafficStats.getTotalTxBytes()
        if (TrafficStats.getTotalRxBytes() == TrafficStats.UNSUPPORTED.toLong()) return -1
        val mobile = (TrafficStats.getMobileRxBytes() + TrafficStats.getMobileTxBytes()).coerceAtLeast(0)
        val uid = Process.myUid()
        val own = (TrafficStats.getUidRxBytes(uid) + TrafficStats.getUidTxBytes(uid)).coerceAtLeast(0)
        return (total - mobile - own).coerceAtLeast(0)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val EXTRA_ACTION = "action"
        private const val TICK_MS = 60_000L

        fun intent(context: Context, action: Action? = null) =
            Intent(context, StatusService::class.java).apply {
                action?.let { putExtra(EXTRA_ACTION, it.name) }
            }

        /** Запускает или останавливает сервис по настройкам. Вызывать из интерфейса. */
        fun sync(context: Context) {
            if (Prefs.serviceNeeded) {
                ContextCompat.startForegroundService(context, intent(context))
            } else {
                context.stopService(intent(context))
            }
        }
    }
}
