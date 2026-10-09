package com.vsatstar.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.MenuItem
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.vsatstar.app.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {
    private lateinit var b: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        b.username.setText(Prefs.username)
        b.password.setText(Prefs.password)
        b.host.setText(Prefs.host)
        b.switchStatusIcon.isChecked = Prefs.showStatusIcon
        b.switchReminder.isChecked = Prefs.limitReminder
        b.switchAutoOff.isChecked = Prefs.autoOff

        b.btnSave.setOnClickListener {
            save()
            Toast.makeText(this, "Сохранено", Toast.LENGTH_SHORT).show()
            finish()
        }

        b.version.text = "VSAT STAR для Android, версия ${BuildConfig.VERSION_NAME}"
        b.github.setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(GITHUB_URL)))
        }
    }

    private fun save() {
        Prefs.username = b.username.text?.toString()?.trim().orEmpty()
        Prefs.password = b.password.text?.toString().orEmpty()
        Prefs.host = b.host.text?.toString().orEmpty()
        Prefs.showStatusIcon = b.switchStatusIcon.isChecked
        Prefs.limitReminder = b.switchReminder.isChecked
        Prefs.autoOff = b.switchAutoOff.isChecked
        StatusService.sync(this)
        Vsat.clearError()
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) {
            finish()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    companion object {
        const val GITHUB_URL = "https://github.com/dima0090142-lgtm/vsat-star"
    }
}
