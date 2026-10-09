package com.vsatstar.app

/**
 * Экспериментальное автоотключение: срабатывает, если за [windowMs] через Wi-Fi прошло
 * меньше [thresholdBytes]. Устойчив к пропускам тиков (телефон спал) - считается
 * время от последней "активности", а не число тиков.
 *
 * [bytes] возвращает счётчик трафика или отрицательное число, если он недоступен.
 */
class IdleWatcher(
    private val now: () -> Long,
    private val bytes: () -> Long,
    private val thresholdBytes: Long = DEFAULT_THRESHOLD_BYTES,
    private val windowMs: Long = DEFAULT_WINDOW_MS,
) {
    private var anchorTime = -1L
    private var anchorBytes = 0L

    fun reset() {
        anchorTime = -1L
    }

    /** Миллисекунд без трафика (по текущему отсчёту). */
    fun idleMs(): Long = if (anchorTime < 0) 0 else now() - anchorTime

    /** true - пора отключать интернет. */
    fun tick(): Boolean {
        val t = now()
        val b = bytes()
        if (b < 0) {
            // Счётчик недоступен - ничего не решаем
            anchorTime = -1L
            return false
        }
        // Первый замер, сброс счётчиков (перезагрузка) или был трафик - отсчёт заново
        if (anchorTime < 0 || b < anchorBytes || b - anchorBytes > thresholdBytes) {
            anchorTime = t
            anchorBytes = b
            return false
        }
        return t - anchorTime >= windowMs
    }

    companion object {
        const val DEFAULT_THRESHOLD_BYTES = 2L * 1024 * 1024
        const val DEFAULT_WINDOW_MS = 60L * 60 * 1000
    }
}
