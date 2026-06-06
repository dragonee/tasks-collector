package org.polybrain.tasks.health.location

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import org.polybrain.tasks.health.MainActivity
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.Breadcrumb
import org.polybrain.tasks.health.data.BreadcrumbStore

/**
 * Foreground service that records a [Breadcrumb] trail while a trip is active.
 *
 * Sampling cadence adapts to screen state — every [ACTIVE_INTERVAL_MS] while
 * the phone is interactive, every [IDLE_INTERVAL_MS] while it's locked — to
 * keep a useful trail without draining the battery. Lifecycle is driven by
 * [TripTracker]; this service just samples while running.
 *
 * Type `location` + a started-from-foreground app means we sample in the
 * background on a while-in-use grant, with no `ACCESS_BACKGROUND_LOCATION`.
 */
class TripLocationService : Service() {

    private lateinit var client: FusedLocationProviderClient
    private lateinit var store: BreadcrumbStore
    private var interactive = true
    private var started = false

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            for (location in result.locations) {
                store.append(
                    Breadcrumb(
                        t = if (location.time > 0) location.time else System.currentTimeMillis(),
                        lat = location.latitude,
                        lng = location.longitude,
                        acc = if (location.hasAccuracy()) location.accuracy else null,
                    )
                )
            }
        }
    }

    // SCREEN_ON/OFF are sticky system broadcasts that must be registered at
    // runtime; flipping interactive re-requests updates at the new cadence.
    private val screenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                Intent.ACTION_SCREEN_ON -> setInteractive(true)
                Intent.ACTION_SCREEN_OFF -> setInteractive(false)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        client = LocationServices.getFusedLocationProviderClient(this)
        store = BreadcrumbStore(this)
        interactive = (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
        ContextCompat.registerReceiver(
            this,
            screenReceiver,
            IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
            },
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!hasLocationPermission()) {
            // Started without the location grant (e.g. the user denied it).
            // Do NOT promote to a location-type foreground service — that throws
            // on Android 14+. Stop cleanly before the start-timeout instead.
            stopSelf()
            return START_NOT_STICKY
        }
        startForegroundNotification()
        if (!started) {
            started = true
            requestUpdates()
        }
        // Re-create the service (and resume sampling) if the OS kills it.
        return START_STICKY
    }

    override fun onDestroy() {
        client.removeLocationUpdates(callback)
        runCatching { unregisterReceiver(screenReceiver) }
        super.onDestroy()
    }

    override fun onBind(intent: Intent): IBinder? = null

    private fun setInteractive(value: Boolean) {
        if (interactive == value || !started) return
        interactive = value
        requestUpdates()
    }

    @SuppressLint("MissingPermission")
    private fun requestUpdates() {
        if (!hasLocationPermission()) return
        client.removeLocationUpdates(callback)
        val intervalMs = if (interactive) ACTIVE_INTERVAL_MS else IDLE_INTERVAL_MS
        val request = LocationRequest.Builder(
            Priority.PRIORITY_BALANCED_POWER_ACCURACY,
            intervalMs,
        ).build()
        client.requestLocationUpdates(request, callback, Looper.getMainLooper())
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED

    private fun startForegroundNotification() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.trip_tracking_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            )
            manager.createNotificationChannel(channel)
        }
        val openApp = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.trip_tracking_notification_title))
            .setContentText(getString(R.string.trip_tracking_notification_text))
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setContentIntent(openApp)
            .build()
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            } else {
                0
            },
        )
    }

    companion object {
        private const val CHANNEL_ID = "trip_location"
        private const val NOTIFICATION_ID = 4201
        private const val ACTIVE_INTERVAL_MS = 30_000L
        private const val IDLE_INTERVAL_MS = 120_000L
    }
}
