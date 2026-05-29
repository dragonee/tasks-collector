package org.polybrain.tasks.health.data

import java.io.IOException
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

object TasksClient {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    // Bare client for direct-to-S3 presigned PUTs. It MUST NOT carry the
    // "Authorization: Token …" header the authed client adds — S3 rejects
    // unexpected auth and we'd leak the API token to the bucket host.
    private val rawClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            })
            .build()
    }

    /** Upload bytes to a presigned PUT URL. Blocking — call off the main thread. */
    fun putToPresignedUrl(url: String, bytes: ByteArray, contentType: String) {
        val body = bytes.toRequestBody(contentType.toMediaType())
        val request = Request.Builder()
            .url(url)
            .put(body)
            .header("Content-Type", contentType)
            .build()
        rawClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("photo upload failed: HTTP ${response.code}")
            }
        }
    }

    fun build(serverUrl: String, apiToken: String): TasksApi {
        val baseUrl = serverUrl.trimEnd('/') + "/"

        val okHttp = OkHttpClient.Builder()
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                    .header("Authorization", "Token $apiToken")
                    .header("Accept", "application/json")
                    .build()
                chain.proceed(request)
            }
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            })
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttp)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(TasksApi::class.java)
    }
}
