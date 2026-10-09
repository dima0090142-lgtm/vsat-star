package com.vsatstar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Ожидаемые значения получены из parse_usage / remaining_minutes Windows-версии. */
class UsageParserTest {
    @Test
    fun starlinkPage() {
        val html = """
            <div class="row"><label>Downloaded</label><span class="usageData">1.25 GB</span></div>
            <div><label>Uploaded</label><span class="usageData big">310.4 MB</span></div>
            <div><label>Remaining Data</label><span class="usageData">8.44 GB</span></div>
            <div><label>Remaining Time</label><span class="usageData">03:07:23</span></div>
        """.trimIndent()
        assertEquals(Usage("1.25 GB", "310.4 MB", "8.44 GB", "03:07:23"), UsageParser.parse(html))
    }

    @Test
    fun vsatPageWithoutRemainingData() {
        val html = """
            <p>Загружено: <span class="usageData">512 MB</span></p>
            <p>Отправлено: <span class="usageData">64&nbsp;MB</span></p>
            <p>Осталось времени: <span class="usageData">1 day 02:00:00</span></p>
        """.trimIndent()
        assertEquals(Usage("512 MB", "64 MB", Usage.UNKNOWN, "1 day 02:00:00"), UsageParser.parse(html))
    }

    @Test
    fun valuesWithoutLabelsAreSortedByFormat() {
        val html = """<span class="usageData">1 GB</span><span class="usageData">2 GB</span><span class="usageData">00:45:00</span>"""
        assertEquals(Usage("1 GB", "2 GB", Usage.UNKNOWN, "00:45:00"), UsageParser.parse(html))
    }

    @Test
    fun loginPageGivesEmptyUsage() {
        assertTrue(UsageParser.parse("<html>login</html>").isEmpty)
    }

    @Test
    fun remainingMinutes() {
        assertEquals(187.3833, UsageParser.remainingMinutes("03:07:23")!!, 0.001)
        assertEquals(1560.0, UsageParser.remainingMinutes("1 day 02:00:00")!!, 0.001)
        assertEquals(135.0, UsageParser.remainingMinutes("2 h 15 min")!!, 0.001)
        assertEquals(45.0, UsageParser.remainingMinutes("45 мин")!!, 0.001)
        assertEquals(8640.0, UsageParser.remainingMinutes("6 days")!!, 0.001)
        assertEquals(1620.0, UsageParser.remainingMinutes("1 ДН 3 Ч")!!, 0.001)
        assertNull(UsageParser.remainingMinutes("?"))
        assertNull(UsageParser.remainingMinutes("abc"))
        assertNull(UsageParser.remainingMinutes(null))
    }
}
