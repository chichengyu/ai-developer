import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class MediaClient(
    private val baseUrl: String = "http://127.0.0.1:8765",
    private val token: String? = null,
) {
    private val client = OkHttpClient()

    private fun builder(path: String): Request.Builder {
        val requestBuilder = Request.Builder().url("$baseUrl$path")
        if (token != null) {
            requestBuilder.header("Authorization", "Bearer $token")
        }
        return requestBuilder
    }

    fun enqueue(kind: String, payload: Map<String, Any?>, dedupeKey: String? = null): String {
        val body = mapOf("kind" to kind, "payload" to payload, "dedupe_key" to dedupeKey)
        val json = JSONObject(body).toString()
        val request = builder("/tasks")
            .post(json.toRequestBody("application/json".toMediaType()))
            .build()
        return client.newCall(request).execute().body!!.string()
    }

    fun task(id: Long): String {
        val request = builder("/tasks/$id").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun taskProgress(id: Long): String {
        val request = builder("/tasks/$id/progress").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun taskEvents(id: Long, after: Int = 0, timeout: Double = 0.0): String {
        val query = if (timeout > 0) "after=$after&timeout=$timeout" else "after=$after"
        val request = builder("/tasks/$id/events?$query").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun depsProgress(): String {
        val request = builder("/deps/progress").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun depsStatus(): String {
        val request = builder("/deps/status").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun formats(): String {
        val request = builder("/formats").build()
        return client.newCall(request).execute().body!!.string()
    }

    fun installDeps(): String {
        val request = builder("/deps/install")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return client.newCall(request).execute().body!!.string()
    }
}
