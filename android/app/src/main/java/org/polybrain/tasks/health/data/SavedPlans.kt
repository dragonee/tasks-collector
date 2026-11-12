package org.polybrain.tasks.health.data

import android.content.Context
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.time.LocalDate
import java.util.UUID
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * The plans of the days the phone has fetched, kept so that the Today list
 * has something to show without a connection: one file per day, the agenda
 * as the server last gave it.
 *
 * Each file names the account that fetched it ([account]): logged in as
 * someone else, or logged out, the phone shows none of them. Days more than
 * [KEEP_DAYS] away from today are thrown away.
 *
 * Takes a [File] root (not a `Context`) so it is unit-testable on the JVM
 * with a temp dir, as the [Outbox] is.
 */
class SavedPlans(private val dir: File) {

    constructor(context: Context) : this(File(context.filesDir, "plans"))

    init {
        dir.mkdirs()
    }

    @Serializable
    data class Saved(
        val account: String,
        /** When it was fetched, epoch milliseconds. */
        val savedAt: Long,
        val agenda: AgendaResponse,
    )

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Keep [agenda] as the plans of [day] (YYYY-MM-DD). */
    fun save(
        account: String,
        day: String,
        agenda: AgendaResponse,
        savedAt: Long = System.currentTimeMillis(),
        today: LocalDate = LocalDate.now(),
    ) {
        // One of its own per write: the screen and the background job may
        // save the same day at once.
        val tmp = File(dir, "$day.${UUID.randomUUID()}.tmp")
        tmp.writeText(json.encodeToString(Saved.serializer(), Saved(account, savedAt, agenda)))
        // A file read while another is written is the old one or the new one.
        Files.move(
            tmp.toPath(),
            fileOf(day).toPath(),
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.ATOMIC_MOVE,
        )
        prune(today)
    }

    /** The plans of [day] last fetched by [account], or null. */
    fun load(account: String, day: String): Saved? {
        val file = fileOf(day)
        if (!file.exists()) return null
        val saved = runCatching {
            json.decodeFromString(Saved.serializer(), file.readText())
        }.getOrNull() ?: return null
        return saved.takeIf { it.account == account }
    }

    private fun prune(today: LocalDate) {
        val keep = today.minusDays(KEEP_DAYS)..today.plusDays(KEEP_DAYS)
        dir.listFiles()?.forEach { file ->
            if (file.name.endsWith(".tmp")) return@forEach
            val day = runCatching { LocalDate.parse(file.name.removeSuffix(".json")) }.getOrNull()
            if (day == null || day !in keep) file.delete()
        }
    }

    private fun fileOf(day: String) = File(dir, "$day.json")

    companion object {
        const val KEEP_DAYS = 14L

        /**
         * Who fetched the plans: the server and the token, hashed. A new
         * login has a new token, so what the last one fetched isn't shown.
         */
        fun account(serverUrl: String, apiToken: String): String =
            MessageDigest.getInstance("SHA-256")
                .digest("$serverUrl\n$apiToken".toByteArray())
                .joinToString("") { "%02x".format(it) }
    }
}

/**
 * Fetch the plans of [today] and of the day after and keep them, so the
 * morning's list is on the phone before it is opened without a connection.
 */
suspend fun SavedPlans.refresh(api: TasksApi, account: String, today: LocalDate) {
    for (day in listOf(today, today.plusDays(1))) {
        save(account, day.toString(), api.agenda(day.toString()), today = today)
    }
}
