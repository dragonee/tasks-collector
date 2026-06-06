package org.polybrain.tasks.health.data

import kotlinx.serialization.Serializable

/**
 * One recorded location sample on a trip's breadcrumb trail.
 *
 * [t] is the sample's wall-clock moment (epoch millis) — the key used to match
 * a photo to where it was taken. Kept deliberately tiny: a long trip records
 * thousands of these, one NDJSON line each.
 */
@Serializable
data class Breadcrumb(
    val t: Long,
    val lat: Double,
    val lng: Double,
    val acc: Float? = null,
)
