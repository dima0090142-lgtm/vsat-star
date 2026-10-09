package com.vsatstar.app

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.TimeInterpolator
import android.animation.ValueAnimator
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.vsatstar.app.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var b: ActivityMainBinding
    private lateinit var appTheme: AppTheme
    private val terminal get() = appTheme == AppTheme.TERMINAL

    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        StatusService.sync(this)
    }

    /** Строка списка: терминал или "Отключить". */
    private class Row(val root: View, val icon: ImageView, val title: TextView, val sub: TextView, val check: ImageView, val tag: TextView)

    private lateinit var rowStarlink: Row
    private lateinit var rowVsat: Row
    private lateinit var rowOff: Row

    override fun onCreate(savedInstanceState: Bundle?) {
        appTheme = applyAppTheme()
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)

        rowStarlink = Row(b.rowStarlink, b.iconStarlink, b.titleStarlink, b.subStarlink, b.checkStarlink, b.tagStarlink)
        rowVsat = Row(b.rowVsat, b.iconVsat, b.titleVsat, b.subVsat, b.checkVsat, b.tagVsat)
        rowOff = Row(b.rowOff, b.iconOff, b.titleOff, b.subOff, b.checkOff, b.tagOff)

        b.rowStarlink.setOnClickListener { act(Action.STARLINK) }
        b.rowVsat.setOnClickListener { act(Action.VSAT) }
        b.rowOff.setOnClickListener { act(Action.DISCONNECT) }
        b.btnRefresh.setOnClickListener { act(Action.USAGE) }
        b.swipeRefresh.setColorSchemeColors(themeColor(R.attr.vsAccent))
        b.swipeRefresh.setProgressBackgroundColorSchemeColor(themeColor(R.attr.vsSurface))
        b.swipeRefresh.setOnRefreshListener {
            Vsat.clearError()
            // Запрос не начался (уже идёт другой) - сразу убираем индикатор
            if (!Vsat.perform(Action.USAGE)) b.swipeRefresh.isRefreshing = Vsat.isBusy
        }
        b.btnOpenSettings.setOnClickListener { openSettings() }

        setupThemeDetails()

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                Vsat.state.collect { render(it) }
            }
        }

        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    /** Мелочи, которые отличают темы друг от друга, помимо цветов. */
    private fun setupThemeDetails() {
        rowOff.check.visibility = View.GONE
        when (appTheme) {
            AppTheme.TERMINAL -> {
                b.toolbar.title = "C:\\VSAT>"
                b.statusLabel.text = "> STATUS"
                b.headerTerminals.text = "== ТЕРМИНАЛ =="
                b.headerTraffic.text = "== ТРАФИК =="
                rowStarlink.title.text = "[1] STARLINK"
                rowVsat.title.text = "[2] VSAT"
                rowOff.title.text = "[0] ОТКЛЮЧИТЬ"
                listOf(rowStarlink, rowVsat, rowOff).forEach {
                    it.icon.visibility = View.GONE
                    it.check.visibility = View.GONE
                    it.tag.visibility = View.VISIBLE
                }
                b.divider1.visibility = View.GONE
                b.divider2.visibility = View.GONE
                b.statusIcon.visibility = View.GONE
                b.statusCursor.visibility = View.VISIBLE
                // Мигающий курсор, как в консоли
                ObjectAnimator.ofFloat(b.statusCursor, View.ALPHA, 1f, 0f).apply {
                    duration = 1000
                    repeatCount = ValueAnimator.INFINITE
                    interpolator = TimeInterpolator { t -> if (t < 0.5f) 0f else 1f }
                    start()
                }
                b.root.useMonospace()
            }
            AppTheme.TELEGRAM -> {
                rowStarlink.check.setImageResource(R.drawable.ic_double_check)
                rowVsat.check.setImageResource(R.drawable.ic_double_check)
            }
            AppTheme.CLASSIC -> Unit
        }
    }

    override fun onStart() {
        super.onStart()
        // Тему поменяли в настройках - перерисовываем экран
        if (Prefs.theme != appTheme) {
            recreate()
            return
        }
        StatusService.sync(this)
        b.credentialsHint.visibility = if (Prefs.hasCredentials) View.GONE else View.VISIBLE
        val s = Vsat.state.value
        if (s.conn.isConnected && Prefs.hasCredentials &&
            (s.usageAt == 0L || SystemClock.elapsedRealtime() - s.usageAt >= Vsat.USAGE_REFRESH_MS)
        ) {
            Vsat.perform(Action.USAGE, quiet = true)
        }
    }

    private fun act(action: Action) {
        Vsat.clearError()
        Vsat.perform(action)
    }

    private fun openSettings() = startActivity(Intent(this, SettingsActivity::class.java))

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == R.id.action_settings) {
            openSettings()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    private fun connColor(conn: ConnState) = themeColor(
        when (conn) {
            ConnState.STARLINK -> R.attr.vsStarlink
            ConnState.VSAT -> R.attr.vsVsat
            ConnState.DISCONNECTED -> R.attr.vsWarn
            ConnState.UNKNOWN -> R.attr.vsNeutral
        }
    )

    private fun tintIcon(icon: ImageView, color: Int) {
        if (appTheme == AppTheme.TELEGRAM) {
            // Как аватарки в Telegram: белый значок на цветном круге
            icon.imageTintList = ColorStateList.valueOf(0xFFFFFFFF.toInt())
            icon.backgroundTintList = ColorStateList.valueOf(color)
        } else {
            icon.imageTintList = ColorStateList.valueOf(color)
            icon.backgroundTintList = ColorStateList.valueOf(ColorUtils.setAlphaComponent(color, 0x24))
        }
    }

    private fun render(s: UiState) {
        val conn = s.conn
        val busy = s.busy != null
        val color = connColor(conn)

        b.statusIcon.setImageResource(Notifier.smallIcon(conn))
        tintIcon(b.statusIcon, color)
        b.statusTitle.text = if (terminal) {
            when (conn) {
                ConnState.STARLINK -> "STARLINK ONLINE"
                ConnState.VSAT -> "VSAT ONLINE"
                ConnState.DISCONNECTED -> "OFFLINE"
                ConnState.UNKNOWN -> "NO CARRIER"
            }
        } else {
            conn.label
        }
        b.statusTitle.setTextColor(if (terminal) color else themeColor(R.attr.vsText))
        b.statusCursor.setTextColor(color)
        b.statusDetail.text = s.busy ?: s.detail
        b.statusDetail.setTextColor(
            themeColor(if (s.isError && !busy) R.attr.vsDanger else R.attr.vsTextSecondary)
        )
        b.progress.visibility = if (busy) View.VISIBLE else View.INVISIBLE
        if (!busy) b.swipeRefresh.isRefreshing = false

        renderTerminalRow(rowStarlink, ConnState.STARLINK, s)
        renderTerminalRow(rowVsat, ConnState.VSAT, s)

        val danger = themeColor(R.attr.vsDanger)
        tintIcon(rowOff.icon, danger)
        rowOff.title.setTextColor(danger)
        rowOff.sub.text = when {
            conn.isConnected -> "Завершить сессию и не тратить лимит"
            else -> "Сейчас не подключено"
        }
        rowOff.tag.text = ""
        rowOff.root.isEnabled = !busy
        rowOff.root.alpha = if (busy) 0.5f else 1f

        b.btnRefresh.isEnabled = !busy
        val u = s.usage
        b.valDownloaded.text = u?.downloaded ?: "—"
        b.valUploaded.text = u?.uploaded ?: "—"
        b.valRemainingData.text = u?.remainingData ?: "—"
        b.valRemainingTime.text = u?.remainingTime ?: "—"
        b.valRemainingTime.setTextColor(themeColor(if (s.lowTime) R.attr.vsWarn else R.attr.vsText))
        b.usageCaption.text = s.usageCaption.ifEmpty { "потяните вниз, чтобы обновить" }
    }

    private fun renderTerminalRow(row: Row, target: ConnState, s: UiState) {
        val active = s.conn == target
        val color = connColor(target)
        val okColor = themeColor(R.attr.vsOk)
        tintIcon(row.icon, color)
        row.check.imageTintList = ColorStateList.valueOf(if (appTheme == AppTheme.TELEGRAM) themeColor(R.attr.vsAccent) else okColor)
        row.check.visibility = if (active && !terminal) View.VISIBLE else View.GONE

        row.sub.text = when {
            active -> if (appTheme == AppTheme.TELEGRAM) "в сети" else "Подключено"
            target == ConnState.STARLINK -> "Спутники на низкой орбите"
            else -> "Геостационарный спутник"
        }
        row.sub.setTextColor(if (active) okColor else themeColor(R.attr.vsTextSecondary))
        row.title.setTextColor(if (terminal && active) color else themeColor(R.attr.vsText))
        row.tag.text = if (active) "[ ON ]" else "[    ]"
        row.tag.setTextColor(if (active) color else themeColor(R.attr.vsTextSecondary))

        // Активная строка слегка подсвечена цветом терминала
        row.root.setBackgroundColor(if (active) ColorUtils.setAlphaComponent(color, 0x14) else 0)
        if (!active) row.root.setBackgroundResource(selectableBackground())
        val busy = s.busy != null
        row.root.isEnabled = !busy && !active
        row.root.alpha = if (busy && !active) 0.5f else 1f
    }

    private fun selectableBackground(): Int {
        val tv = android.util.TypedValue()
        theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
        return tv.resourceId
    }
}
