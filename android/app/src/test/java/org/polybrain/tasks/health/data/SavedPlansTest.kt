package org.polybrain.tasks.health.data

import java.io.File
import java.nio.file.Files
import java.time.LocalDate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

class SavedPlansTest {

    private lateinit var dir: File
    private lateinit var plans: SavedPlans

    private val today = LocalDate.of(2026, 11, 12)
    private val account = SavedPlans.account("https://tasks", "token")

    private fun agenda(vararg texts: String) = AgendaResponse(
        daily = AgendaPlan(
            thread = "Daily",
            pubDate = today.toString(),
            tasks = texts.mapIndexed { i, text -> Task(id = "t$i", text = text, done = i == 0) },
        ),
    )

    @Before
    fun setUp() {
        dir = Files.createTempDirectory("plans-test").toFile()
        plans = SavedPlans(dir)
    }

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    @Test
    fun `the plans of a day come back as they were fetched`() {
        plans.save(account, "2026-11-12", agenda("Call the client", "Write the report"), savedAt = 42L, today = today)

        val saved = plans.load(account, "2026-11-12")!!

        assertEquals(agenda("Call the client", "Write the report"), saved.agenda)
        assertEquals(42L, saved.savedAt)
    }

    @Test
    fun `a day saved again is the later fetch`() {
        plans.save(account, "2026-11-12", agenda("Before"), today = today)
        plans.save(account, "2026-11-12", agenda("After"), today = today)

        assertEquals(agenda("After"), plans.load(account, "2026-11-12")!!.agenda)
    }

    @Test
    fun `a day never fetched has nothing`() {
        assertNull(plans.load(account, "2026-11-13"))
    }

    @Test
    fun `another account sees nothing of what this one fetched`() {
        plans.save(account, "2026-11-12", agenda("Mine"), today = today)

        assertNull(plans.load(SavedPlans.account("https://tasks", "another token"), "2026-11-12"))
        assertNull(plans.load(SavedPlans.account("https://elsewhere", "token"), "2026-11-12"))
    }

    @Test
    fun `days more than two weeks away are thrown away`() {
        plans.save(account, "2026-10-01", agenda("Long ago"), today = today.minusDays(42))
        plans.save(account, "2026-12-31", agenda("Far ahead"), today = today.plusDays(49))
        plans.save(account, "2026-10-29", agenda("Two weeks ago"), today = today.minusDays(14))

        plans.save(account, "2026-11-12", agenda("Today"), today = today)

        assertNull(plans.load(account, "2026-10-01"))
        assertNull(plans.load(account, "2026-12-31"))
        assertEquals(agenda("Two weeks ago"), plans.load(account, "2026-10-29")!!.agenda)
    }

    @Test
    fun `a broken file is nothing saved`() {
        File(dir, "2026-11-12.json").writeText("{not json")

        assertNull(plans.load(account, "2026-11-12"))
    }

    @Test
    fun `the account is a hash, not the token`() {
        assertEquals(64, account.length)
        assertFalse(account.contains("token"))
        assertNotEquals(account, SavedPlans.account("https://tasks", "token2"))
    }
}
