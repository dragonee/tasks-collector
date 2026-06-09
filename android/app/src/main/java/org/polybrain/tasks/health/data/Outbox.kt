package org.polybrain.tasks.health.data

import android.content.Context
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID
import kotlinx.serialization.json.Json

/**
 * Durable, file-backed queue of trip writes (see [OutboxItem]).
 *
 * Each item is one JSON file in [dir]; a photo's bytes live in a sibling file.
 * Filenames are prefixed with a zero-padded `createdAt`, so a plain
 * lexicographic sort of the directory yields chronological (oldest-first)
 * delivery order. The directory is the single source of truth — no in-memory
 * index — so it survives process death and is read fresh on every drain.
 *
 * Takes a [File] root (not a `Context`) so it is unit-testable on the JVM with
 * a temp dir; [Context] callers use the convenience constructor.
 */
class Outbox(private val dir: File) {

    constructor(context: Context) : this(File(context.filesDir, "outbox"))

    init {
        dir.mkdirs()
    }

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun enqueueNote(storyId: Long, comment: String, published: String): OutboxItem {
        val item = OutboxItem(
            id = UUID.randomUUID().toString(),
            kind = OutboxItem.Kind.NOTE,
            storyId = storyId,
            comment = comment,
            published = published,
            createdAt = System.currentTimeMillis(),
        )
        write(item)
        return item
    }

    fun enqueuePhoto(
        storyId: Long?,
        comment: String,
        published: String,
        contentType: String,
        bytes: ByteArray,
    ): OutboxItem {
        val id = UUID.randomUUID().toString()
        val createdAt = System.currentTimeMillis()
        val photoName = baseName(createdAt, id) + "." + extFor(contentType)
        File(dir, photoName).writeBytes(bytes)
        val item = OutboxItem(
            id = id,
            kind = OutboxItem.Kind.PHOTO,
            storyId = storyId,
            comment = comment,
            published = published,
            createdAt = createdAt,
            contentType = contentType,
            photoFile = photoName,
        )
        write(item)
        return item
    }

    /** All queued items, oldest first. */
    fun all(): List<OutboxItem> =
        (dir.listFiles { f -> f.isFile && f.name.endsWith(".json") } ?: emptyArray())
            .sortedBy { it.name }
            .mapNotNull { read(it) }

    fun forStory(storyId: Long): List<OutboxItem> = all().filter { it.storyId == storyId }

    /** Standalone (storyless) items, oldest first. */
    fun standalone(): List<OutboxItem> = all().filter { it.storyId == null }

    /** Persist a mutated item back to its file (same name — id/createdAt are immutable). */
    fun update(item: OutboxItem) = write(item)

    /** Remove an item's JSON and its photo file (if any). */
    fun remove(item: OutboxItem) {
        File(dir, jsonName(item)).delete()
        photoFile(item)?.delete()
    }

    fun photoFile(item: OutboxItem): File? = item.photoFile?.let { File(dir, it) }

    fun photoBytes(item: OutboxItem): ByteArray? =
        photoFile(item)?.takeIf { it.exists() }?.readBytes()

    private fun write(item: OutboxItem) {
        val target = File(dir, jsonName(item))
        val tmp = File(dir, jsonName(item) + ".tmp")
        tmp.writeText(json.encodeToString(OutboxItem.serializer(), item))
        // Atomic replace so a crash mid-write never leaves a half-written item.
        Files.move(
            tmp.toPath(),
            target.toPath(),
            StandardCopyOption.REPLACE_EXISTING,
        )
    }

    private fun read(file: File): OutboxItem? = runCatching {
        json.decodeFromString(OutboxItem.serializer(), file.readText())
    }.getOrNull()

    private fun jsonName(item: OutboxItem) = baseName(item.createdAt, item.id) + ".json"

    private companion object {
        fun baseName(createdAt: Long, id: String) =
            "%016d-%s".format(createdAt, id.take(8))

        fun extFor(contentType: String): String = when (contentType.lowercase()) {
            "image/jpeg", "image/jpg" -> "jpg"
            "image/png" -> "png"
            "image/webp" -> "webp"
            "image/heic", "image/heif" -> "heic"
            else -> "img"
        }
    }
}
