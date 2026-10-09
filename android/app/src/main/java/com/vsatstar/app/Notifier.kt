package com.vsatstar.app

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object Notifier {
    const val STATUS_ID = 1
    private const val REMINDER_ID = 2
    private const val AUTO_OFF_ID = 3

    private const val CH_STATUS = "status"
    private const val CH_ALERTS = "alerts"

    fun createChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CH_STATUS, "Текущее подключение", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Значок активного терминала в строке состояния и быстрые кнопки"
                setShowBadge(false)
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CH_ALERTS, "Предупреждения", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Конец дневного лимита и автоотключение"
            }
        )
    }

    fun smallIcon(conn: ConnState) = when (conn) {
        ConnState.STARLINK -> R.drawable.ic_starlink
        ConnState.VSAT -> R.drawable.ic_vsat
        ConnState.DISCONNECTED -> R.drawable.ic_power
        ConnState.UNKNOWN -> R.drawable.ic_unknown
    }

    fun accent(context: Context, conn: ConnState) = ContextCompat.getColor(
        context,
        when (conn) {
            ConnState.STARLINK -> R.color.starlink
            ConnState.VSAT -> R.color.vsat
            ConnState.DISCONNECTED -> R.color.warn
            ConnState.UNKNOWN -> R.color.neutral
        }
    )

    private fun openApp(context: Context) = PendingIntent.getActivity(
        context, 0,
        Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun serviceAction(context: Context, action: Action) = PendingIntent.getService(
        context, action.ordinal + 10,
        StatusService.intent(context, action),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    fun buildStatus(context: Context, state: UiState, idleMinutes: Long?): Notification {
        val conn = state.conn
        val title = when {
            state.busy != null -> state.busy
            conn.isConnected -> "${conn.label} - подключено"
            else -> conn.label
        }
        val text = buildList {
            state.usage?.let { u ->
                if (u.remainingTime != Usage.UNKNOWN) add("Осталось ${u.remainingTime}")
                if (u.remainingData != Usage.UNKNOWN) add(u.remainingData)
            }
            if (isEmpty() && state.detail.isNotEmpty()) add(state.detail)
            if (idleMinutes != null && idleMinutes >= 5) add("без трафика $idleMinutes мин")
        }.joinToString(" · ")

        val builder = NotificationCompat.Builder(context, CH_STATUS)
            .setSmallIcon(smallIcon(conn))
            .setColor(accent(context, conn))
            .setContentTitle(title)
            .setContentText(text.ifEmpty { null })
            .setContentIntent(openApp(context))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setShowWhen(false)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)

        if (state.busy == null) {
            if (conn != ConnState.STARLINK) builder.addAction(R.drawable.ic_starlink, "Starlink", serviceAction(context, Action.STARLINK))
            if (conn != ConnState.VSAT) builder.addAction(R.drawable.ic_vsat, "VSAT", serviceAction(context, Action.VSAT))
            if (conn.isConnected) builder.addAction(R.drawable.ic_power, "Отключить", serviceAction(context, Action.DISCONNECT))
        }
        return builder.build()
    }

    fun showLimitReminder(context: Context, text: String) =
        alert(context, REMINDER_ID, "Заканчивается лимит", text)

    fun showAutoOff(context: Context) =
        alert(context, AUTO_OFF_ID, "Интернет отключён", "Не было трафика больше часа - сессия завершена, чтобы не тратить лимит")

    private fun alert(context: Context, id: Int, title: String, text: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return
        val n = NotificationCompat.Builder(context, CH_ALERTS)
            .setSmallIcon(R.drawable.ic_warning)
            .setColor(ContextCompat.getColor(context, R.color.warn))
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(openApp(context))
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(id, n)
    }
}
