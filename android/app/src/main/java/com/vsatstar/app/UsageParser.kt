package com.vsatstar.app

/** Данные со страницы card-usage. "?" - значение не найдено. */
data class Usage(
    val downloaded: String = UNKNOWN,
    val uploaded: String = UNKNOWN,
    val remainingData: String = UNKNOWN,
    val remainingTime: String = UNKNOWN,
) {
    val isEmpty: Boolean
        get() = listOf(downloaded, uploaded, remainingData, remainingTime).all { it == UNKNOWN }

    companion object {
        const val UNKNOWN = "?"
    }
}

/**
 * Разбор страницы трафика - перенос parse_usage / remaining_minutes из terminal_switch.py.
 * Набор полей зависит от терминала (на VSAT "остатка данных" может не быть), поэтому значения
 * раскладываются не по позиции, а по подписи рядом и по формату: "04:12:33" / "6 days" - время,
 * "1.2 GB" - объём.
 */
object UsageParser {
    private const val DOWNLOADED = "downloaded"
    private const val UPLOADED = "uploaded"
    private const val REMAINING_DATA = "remaining_data"
    private const val REMAINING_TIME = "remaining_time"

    // Буква/цифра и "конец слова" как \w / \b в Python. Флаг (?U) не используем:
    // на Android (ICU) он не поддерживается. Регистр снимаем через lowercase().
    private const val W = "[\\p{L}\\p{N}_]"
    private const val END = "(?![\\p{L}\\p{N}_])"

    private val usageSpan = Regex(
        "(?i)<span[^>]*class=\"[^\"]*usageData[^\"]*\"[^>]*>\\s*([^<]*?)\\s*</span>"
    )
    private val tag = Regex("<[^>]+>")
    private val timeRe = Regex(
        "\\d+:\\d{2}" +
            "|\\d+\\s*(?:d|h|min|mins|minutes?|hours?|days?|sec|seconds?|дн$W*|ч|час$W*|мин$W*|сек$W*)$END"
    )
    private val dataRe = Regex("\\d\\s*(?:[kmgt]i?b|bytes?|[кмгт]б|байт$W*)$END")
    private val daysRe = Regex("(\\d+)\\s*(?:d|days?|дн$W*)$END")
    private val hmsRe = Regex("(\\d+):(\\d{2})(?::(\\d{2}))?")
    private val hoursRe = Regex("(\\d+)\\s*(?:h|hours?|ч|час$W*)$END")
    private val minsRe = Regex("(\\d+)\\s*(?:m|min|mins|minutes?|мин$W*)$END")

    // Порядок важен: "Remaining time" должно сработать раньше общего "remaining"
    private val labelHints = listOf(
        REMAINING_TIME to listOf("time", "врем", "minute", "минут"),
        DOWNLOADED to listOf("download", "загруж", "скачан", "входящ", "received"),
        UPLOADED to listOf("upload", "отправ", "выгруж", "исходящ", "sent"),
        REMAINING_DATA to listOf("remaining", "left", "остат", "quota", "balance", "data", "трафик"),
    )

    private enum class Kind { TIME, DATA, OTHER }

    private fun valueKind(value: String): Kind {
        val lower = value.lowercase()
        return when {
            timeRe.containsMatchIn(lower) -> Kind.TIME
            dataRe.containsMatchIn(lower) -> Kind.DATA
            else -> Kind.OTHER
        }
    }

    private fun labelKey(text: String): String? {
        val lower = text.lowercase()
        return labelHints.firstOrNull { (_, hints) -> hints.any { it in lower } }?.first
    }

    fun parse(html: String): Usage {
        data class Item(val key: String?, val kind: Kind, val value: String)

        val items = mutableListOf<Item>()
        var prevEnd = 0
        for (m in usageSpan.findAll(html)) {
            val rawLabel = unescape(tag.replace(html.substring(prevEnd, m.range.first), " "))
            val label = rawLabel.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ").takeLast(60)
            prevEnd = m.range.last + 1
            val value = unescape(m.groupValues[1]).trim()
            if (value.isNotEmpty()) items += Item(labelKey(label), valueKind(value), value)
        }

        val result = linkedMapOf<String, String>()
        val leftovers = mutableListOf<Pair<Kind, String>>()
        for ((rawKey, kind, value) in items) {
            // Формат важнее подписи: время не может быть объёмом и наоборот
            var key = rawKey
            if ((key == REMAINING_TIME && kind == Kind.DATA) || (key != REMAINING_TIME && kind == Kind.TIME)) {
                key = null
            }
            if (key != null && key !in result) result[key] = value else leftovers += kind to value
        }

        for ((kind, value) in leftovers) {
            val slots = when (kind) {
                Kind.TIME -> listOf(REMAINING_TIME)
                Kind.DATA -> listOf(DOWNLOADED, UPLOADED, REMAINING_DATA)
                Kind.OTHER -> listOf(DOWNLOADED, UPLOADED, REMAINING_DATA, REMAINING_TIME)
            }
            slots.firstOrNull { it !in result }?.let { result[it] = value }
        }

        return Usage(
            downloaded = result[DOWNLOADED] ?: Usage.UNKNOWN,
            uploaded = result[UPLOADED] ?: Usage.UNKNOWN,
            remainingData = result[REMAINING_DATA] ?: Usage.UNKNOWN,
            remainingTime = result[REMAINING_TIME] ?: Usage.UNKNOWN,
        )
    }

    /** "03:07:23" -> 187.4, "1 day 02:00:00" -> 1560. null, если время не распознано. */
    fun remainingMinutes(raw: String?): Double? {
        if (raw.isNullOrBlank() || raw == Usage.UNKNOWN) return null
        val text = raw.lowercase()
        var total = 0.0
        var found = false
        daysRe.find(text)?.let {
            total += it.groupValues[1].toInt() * 1440
            found = true
        }
        val hms = hmsRe.find(text)
        if (hms != null) {
            val sec = hms.groupValues[3].ifEmpty { "0" }.toInt()
            total += hms.groupValues[1].toInt() * 60 + hms.groupValues[2].toInt() + sec / 60.0
            found = true
        } else {
            hoursRe.find(text)?.let {
                total += it.groupValues[1].toInt() * 60
                found = true
            }
            minsRe.find(text)?.let {
                total += it.groupValues[1].toInt()
                found = true
            }
        }
        return if (found) total else null
    }

    private val entity = Regex("&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z]+);")
    private val named = mapOf(
        "amp" to "&", "lt" to "<", "gt" to ">", "quot" to "\"", "apos" to "'", "nbsp" to "\u00A0",
    )

    private fun unescape(text: String): String = entity.replace(text) { m ->
        val body = m.groupValues[1]
        when {
            body.startsWith("#x") || body.startsWith("#X") ->
                body.substring(2).toIntOrNull(16)?.let { String(Character.toChars(it)) } ?: m.value
            body.startsWith("#") ->
                body.substring(1).toIntOrNull()?.let { String(Character.toChars(it)) } ?: m.value
            else -> named[body.lowercase()] ?: m.value
        }
    }
}
