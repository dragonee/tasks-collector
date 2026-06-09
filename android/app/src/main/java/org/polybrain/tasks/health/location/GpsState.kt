package org.polybrain.tasks.health.location

/**
 * Where a Ready [GpsState] fix came from: a live GPS read (notes and standalone
 * photos, recorded "now") or the trip's recorded breadcrumb track (trip photos,
 * located at their capture time).
 */
enum class GpsSource { LIVE, TRACK }

/**
 * GPS resolution state shared by the add-note and add-photo dialogs. The dialog
 * reads this to decide whether to enable the "Save with location" button and
 * what hint to show.
 */
sealed class GpsState {
    object Idle : GpsState()
    object Waiting : GpsState()
    data class Ready(
        val fix: LocationFix,
        val source: GpsSource = GpsSource.LIVE,
        // For TRACK: the photo's capture time, shown in the dialog hint.
        val atMillis: Long? = null,
    ) : GpsState()
    object Denied : GpsState()
    object Unavailable : GpsState()
}
