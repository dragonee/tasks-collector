package org.polybrain.tasks.health.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull

data class LocationFix(
    val lat: Double,
    val lng: Double,
    val accuracyMeters: Float?,
)

/**
 * Resolves a single fresh location fix on demand.
 *
 * Use [currentFix] from a coroutine; it returns null when permission is
 * missing, the request times out, or the platform returns no location.
 * Callers should treat null as "no GPS available" and either gate the
 * action behind a permission request or offer a no-location override.
 */
class LocationProvider(context: Context) {

    private val appContext = context.applicationContext
    private val client: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(appContext)

    fun hasFineLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            appContext, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    suspend fun currentFix(timeoutMs: Long = 10_000): LocationFix? {
        if (!hasFineLocationPermission()) return null

        val request = CurrentLocationRequest.Builder()
            .setPriority(Priority.PRIORITY_HIGH_ACCURACY)
            .setMaxUpdateAgeMillis(30_000)
            .build()

        return withTimeoutOrNull(timeoutMs) {
            val cancel = CancellationTokenSource()
            try {
                suspendCancellableCoroutine { cont ->
                    cont.invokeOnCancellation { cancel.cancel() }
                    client.getCurrentLocation(request, cancel.token)
                        .addOnSuccessListener { loc ->
                            cont.resume(
                                loc?.let {
                                    LocationFix(
                                        lat = it.latitude,
                                        lng = it.longitude,
                                        accuracyMeters =
                                            if (it.hasAccuracy()) it.accuracy else null,
                                    )
                                }
                            )
                        }
                        .addOnFailureListener { cont.resume(null) }
                        .addOnCanceledListener { cont.resume(null) }
                }
            } finally {
                cancel.cancel()
            }
        }
    }
}
