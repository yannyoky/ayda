package app.ayda.android.auth

import app.ayda.shared.TokenStore
import app.ayda.shared.Tokens
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File

/** Encrypts and decrypts small blobs; on a device the key lives in the Android Keystore. */
interface TokenCipher {
    fun encrypt(plain: ByteArray): ByteArray

    fun decrypt(sealed: ByteArray): ByteArray
}

/**
 * Keeps the tokens in one encrypted file in the app's private storage (ADR 0009).
 * If the file cannot be decrypted (the key is gone after a reinstall or a restore),
 * it is dropped and the user signs in again.
 */
class EncryptedTokenStore(
    private val file: File,
    private val cipher: TokenCipher,
) : TokenStore {
    private val lock = Mutex()
    private var cached: Tokens? = null
    private var loaded = false

    override suspend fun load(): Tokens? =
        lock.withLock {
            if (!loaded) {
                cached = withContext(Dispatchers.IO) { read() }
                loaded = true
            }
            cached
        }

    override suspend fun save(tokens: Tokens) =
        lock.withLock {
            withContext(Dispatchers.IO) { write(tokens) }
            cached = tokens
            loaded = true
        }

    override suspend fun clear() =
        lock.withLock {
            withContext(Dispatchers.IO) { file.delete() }
            cached = null
            loaded = true
        }

    private fun read(): Tokens? {
        if (!file.exists()) return null
        return runCatching {
            val stored = Json.decodeFromString<Stored>(cipher.decrypt(file.readBytes()).decodeToString())
            Tokens(stored.access, stored.refresh)
        }.getOrElse {
            file.delete()
            null
        }
    }

    private fun write(tokens: Tokens) {
        val sealed =
            cipher.encrypt(
                Json.encodeToString(Stored(tokens.accessToken, tokens.refreshToken)).encodeToByteArray(),
            )
        val tmp = File(file.parentFile, "${file.name}.tmp")
        tmp.writeBytes(sealed)
        if (!tmp.renameTo(file)) {
            file.delete()
            check(tmp.renameTo(file)) { "Could not store the tokens" }
        }
    }

    @Serializable
    private data class Stored(
        val access: String,
        val refresh: String,
    )
}
