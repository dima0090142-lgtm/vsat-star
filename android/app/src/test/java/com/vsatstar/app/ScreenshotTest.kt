package com.vsatstar.app

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Looper
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/**
 * Рисует экраны во всех темах в app/build/screenshots - чтобы посмотреть оформление
 * без телефона. CI выкладывает картинки рядом с APK.
 */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w393dp-h852dp-xxhdpi")
class ScreenshotTest {
    private val outDir = File("build/screenshots").apply { mkdirs() }

    private fun connectedState() = UiState(
        conn = ConnState.STARLINK,
        detail = "Подключено 09.10 14:32",
        usage = Usage("1.25 GB", "310.4 MB", "8.44 GB", "03:07:23"),
        usageCaption = "обновлено в 14:35",
        usageAt = SystemClock.elapsedRealtime(),
    )

    private fun capture(activity: Activity, name: String) {
        shadowOf(Looper.getMainLooper()).idle()
        val v = activity.window.decorView
        val bmp = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888)
        v.draw(Canvas(bmp))
        File(outDir, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun prepare(theme: AppTheme, night: Boolean) {
        RuntimeEnvironment.setQualifiers(if (night) "+night" else "+notnight")
        Prefs.username = "crew"
        Prefs.password = "secret"
        Prefs.theme = theme
        Vsat.previewState(connectedState())
    }

    @Test
    fun mainScreens() {
        for (theme in AppTheme.entries) {
            val modes = if (theme == AppTheme.TERMINAL) listOf(true) else listOf(false, true)
            for (night in modes) {
                prepare(theme, night)
                val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
                capture(activity, "main_${theme.name.lowercase()}${if (night) "_dark" else ""}")
            }
        }
    }

    @Test
    fun settingsScreens() {
        for (theme in AppTheme.entries) {
            prepare(theme, night = false)
            val activity = Robolectric.buildActivity(SettingsActivity::class.java).setup().get()
            capture(activity, "settings_${theme.name.lowercase()}")
        }
    }
}
