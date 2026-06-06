package org.polybrain.tasks.health.data

import android.content.Context
import java.io.File
import kotlinx.serialization.json.Json

/**
 * Append-only local log of a trip's location [Breadcrumb]s.
 *
 * One JSON object per line (NDJSON) in [file], so each new sample is a cheap
 * append — no rewrite of the growing file. The location service is the only
 * writer (single-threaded callback); readers tolerate a torn final line via
 * per-line parsing. Takes a [File] (Context convenience ctor) so it is
 * unit-testable on the JVM with a temp file, mirroring [Outbox].
 */
class BreadcrumbStore(private val file: File) {

    constructor(context: Context) : this(File(context.filesDir, "breadcrumbs.log"))

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun append(crumb: Breadcrumb) {
        file.parentFile?.mkdirs()
        // Append a single line; FileWriter(append=true) keeps the O(1) cost.
        java.io.FileWriter(file, true).use { w ->
            w.append(json.encodeToString(Breadcrumb.serializer(), crumb))
            w.append('\n')
        }
    }

    /** All breadcrumbs, oldest first. Skips any unparseable (e.g. torn) line. */
    fun all(): List<Breadcrumb> {
        if (!file.exists()) return emptyList()
        return file.readLines()
            .mapNotNull { line ->
                if (line.isBlank()) {
                    null
                } else {
                    runCatching { json.decodeFromString(Breadcrumb.serializer(), line) }.getOrNull()
                }
            }
            .sortedBy { it.t }
    }

    fun lastAtOrBefore(t: Long): Breadcrumb? = all().lastOrNull { it.t <= t }

    fun firstAtOrAfter(t: Long): Breadcrumb? = all().firstOrNull { it.t >= t }

    fun clear() {
        file.delete()
    }
}
