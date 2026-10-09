package com.vsatstar.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.Menu
import android.view.MenuItem
import android.view.View
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.button.MaterialButton
import com.vsatstar.app.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var b: ActivityMainBinding

    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        StatusService.sync(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)

        b.btnStarlink.setOnClickListener { act(Action.STARLINK) }
        b.btnVsat.setOnClickListener { act(Action.VSAT) }
        b.btnDisconnect.setOnClickListener { act(Action.DISCONNECT) }
        b.btnRefresh.setOnClickListener { act(Action.USAGE) }
        b.btnOpenSettings.setOnClickListener { openSettings() }

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

    override fun onStart() {
        super.onStart()
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

    private fun render(s: UiState) {
        val conn = s.conn
        val accent = Notifier.accent(this, conn)

        b.statusIcon.setImageResource(Notifier.smallIcon(conn))
        b.statusIcon.imageTintList = ColorStateList.valueOf(accent)
        b.statusTitle.text = if (conn.isConnected) "Активен: ${conn.label}" else conn.label
        b.statusDetail.text = s.busy ?: s.detail
        b.statusDetail.setTextColor(
            ContextCompat.getColor(this, if (s.isError && s.busy == null) R.color.danger else R.color.text_secondary)
        )
        b.progress.visibility = if (s.busy != null) View.VISIBLE else View.INVISIBLE

        val enabled = s.busy == null
        listOf(b.btnStarlink, b.btnVsat, b.btnDisconnect, b.btnRefresh).forEach { it.isEnabled = enabled }
        styleTerminal(b.btnStarlink, conn == ConnState.STARLINK, R.color.starlink)
        styleTerminal(b.btnVsat, conn == ConnState.VSAT, R.color.vsat)

        val u = s.usage
        b.valDownloaded.text = u?.downloaded ?: "—"
        b.valUploaded.text = u?.uploaded ?: "—"
        b.valRemainingData.text = u?.remainingData ?: "—"
        b.valRemainingTime.text = u?.remainingTime ?: "—"
        b.valRemainingTime.setTextColor(
            ContextCompat.getColor(this, if (s.lowTime) R.color.warn else R.color.text_primary)
        )
        b.usageCaption.text = s.usageCaption.ifEmpty { "авто каждые 10 мин" }
    }

    private fun styleTerminal(btn: MaterialButton, active: Boolean, colorRes: Int) {
        val color = ContextCompat.getColor(this, colorRes)
        val onColor = ContextCompat.getColor(this, R.color.on_accent)
        btn.backgroundTintList = ColorStateList.valueOf(if (active) color else ContextCompat.getColor(this, R.color.surface_variant))
        val fg = if (active) onColor else color
        btn.setTextColor(fg)
        btn.iconTint = ColorStateList.valueOf(fg)
        btn.strokeColor = ColorStateList.valueOf(color)
    }
}
