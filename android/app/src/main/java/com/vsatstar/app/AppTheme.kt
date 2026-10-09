package com.vsatstar.app

import android.app.Activity
import android.graphics.Typeface
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.annotation.AttrRes
import androidx.annotation.ColorInt

/** Темы оформления, выбираются в настройках. */
enum class AppTheme(val styleRes: Int) {
    CLASSIC(R.style.Theme_VsatStar),
    TELEGRAM(R.style.Theme_VsatStar_Telegram),
    TERMINAL(R.style.Theme_VsatStar_Terminal);

    companion object {
        fun of(name: String?) = entries.firstOrNull { it.name == name } ?: CLASSIC
    }
}

/** Вызывать до super.onCreate(). Возвращает применённую тему. */
fun Activity.applyAppTheme(): AppTheme {
    val theme = Prefs.theme
    setTheme(theme.styleRes)
    return theme
}

@ColorInt
fun Activity.themeColor(@AttrRes attr: Int): Int {
    val tv = TypedValue()
    theme.resolveAttribute(attr, tv, true)
    return tv.data
}

/** Моноширинный шрифт для всего экрана - для темы "Терминал". */
fun View.useMonospace() {
    when (this) {
        is TextView -> typeface = Typeface.create(Typeface.MONOSPACE, typeface?.style ?: Typeface.NORMAL)
        is ViewGroup -> for (i in 0 until childCount) getChildAt(i).useMonospace()
    }
}
