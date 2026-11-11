package org.polybrain.tasks.health.data

import java.io.IOException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.FormBody
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

    // Bare client for direct-to-S3 presigned PUTs, and for logging in and
    // out (which is done without a token, or to get rid of one). It MUST NOT
    // carry the "Authorization: Token …" header the authed client adds — S3
    // rejects unexpected auth and we'd leak the API token to the bucket host.
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

    /**
     * Trade the code of a login for the app's token (see [OAuthLogin]).
     * Blocking — call off the main thread. Throws when the server refuses,
     * with what it said.
     */
    fun exchangeCode(pending: OAuthLogin.Pending, code: String, redirectUri: String): String {
        val form = FormBody.Builder()
            .add("grant_type", "authorization_code")
            .add("code", code)
            .add("code_verifier", pending.verifier)
            .add("client_id", OAuthLogin.CLIENT_ID)
            .add("redirect_uri", redirectUri)
            .build()
        val request = Request.Builder()
            .url("${pending.serverUrl}/oauth/token/")
            .post(form)
            .header("Accept", "application/json")
            .build()
        rawClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            val answer = runCatching { json.parseToJsonElement(body).jsonObject }.getOrNull()
            if (!response.isSuccessful) {
                val error = answer?.get("error")?.jsonPrimitive?.content
                throw IOException("login refused: ${error ?: "HTTP ${response.code}"}")
            }
            return answer?.get("access_token")?.jsonPrimitive?.content
                ?: throw IOException("the server sent no token")
        }
    }

    /**
     * Tell the server to forget a token: the app logging out. Blocking —
     * call off the main thread. Throws when the server can't be told.
     */
    fun revokeToken(serverUrl: String, apiToken: String) {
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/oauth/revoke/")
            .post(FormBody.Builder().add("token", apiToken).build())
            .build()
        rawClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("logout failed: HTTP ${response.code}")
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
