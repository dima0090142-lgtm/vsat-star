package com.vsatstar.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class IdleWatcherTest {
    private var time = 0L
    private var bytes = 0L
    private val minute = 60_000L
    private val mb = 1024L * 1024

    private fun watcher() = IdleWatcher(now = { time }, bytes = { bytes }, thresholdBytes = 2 * mb, windowMs = 60 * minute)

    @Test
    fun firesAfterHourWithoutTraffic() {
        val w = watcher()
        assertFalse(w.tick())
        repeat(59) {
            time += minute
            bytes += 10 * 1024 // фоновые крохи
            assertFalse(w.tick())
        }
        time += minute
        assertTrue(w.tick())
    }

    @Test
    fun trafficRestartsCountdown() {
        val w = watcher()
        w.tick()
        time += 50 * minute
        bytes += 5 * mb
        assertFalse(w.tick())
        time += 50 * minute
        assertFalse(w.tick())
        time += 10 * minute
        assertTrue(w.tick())
    }

    @Test
    fun longSleepCountsAsIdle() {
        val w = watcher()
        w.tick()
        time += 3 * 60 * minute
        assertTrue(w.tick())
    }

    @Test
    fun counterResetOrUnsupportedDoesNotFire() {
        val w = watcher()
        bytes = 100 * mb
        w.tick()
        time += 61 * minute
        bytes = 0 // перезагрузка обнулила счётчики
        assertFalse(w.tick())
        time += 61 * minute
        bytes = -1
        assertFalse(w.tick())
    }

    @Test
    fun resetStartsOver() {
        val w = watcher()
        w.tick()
        time += 59 * minute
        w.reset()
        assertFalse(w.tick())
        time += 30 * minute
        assertFalse(w.tick())
    }
}
