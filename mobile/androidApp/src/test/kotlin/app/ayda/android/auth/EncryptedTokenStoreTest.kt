package app.ayda.android.auth

import app.ayda.shared.Tokens
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class EncryptedTokenStoreTest {
    @get:Rule
    val folder = TemporaryFolder()

    /** The same AES-GCM as on a device, with a key in memory instead of the Keystore. */
    private class MemoryCipher(
        private val key: SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey(),
    ) : TokenCipher {
        override fun encrypt(plain: ByteArray): ByteArray {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key) }
            return cipher.iv + cipher.doFinal(plain)
        }

        override fun decrypt(sealed: ByteArray): ByteArray {
            val cipher =
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, sealed, 0, 12))
                }
            return cipher.doFinal(sealed, 12, sealed.size - 12)
        }
    }

    @Test
    fun tokensSurviveARestartAndAreNotStoredInPlainText() =
        runTest {
            val file = folder.root.resolve("tokens.bin")
            val cipher = MemoryCipher()
            EncryptedTokenStore(file, cipher).save(Tokens("access-1", "refresh-1"))

            val reopened = EncryptedTokenStore(file, cipher)

            assertEquals(Tokens("access-1", "refresh-1"), reopened.load())
            assertFalse(file.readBytes().decodeToString().contains("refresh-1"))
        }

    @Test
    fun clearRemovesTheFile() =
        runTest {
            val file = folder.root.resolve("tokens.bin")
            val store = EncryptedTokenStore(file, MemoryCipher())
            store.save(Tokens("a", "r"))

            store.clear()

            assertNull(store.load())
            assertFalse(file.exists())
        }

    @Test
    fun aFileFromAnotherKeyIsDroppedInsteadOfCrashing() =
        runTest {
            val file = folder.root.resolve("tokens.bin")
            EncryptedTokenStore(file, MemoryCipher()).save(Tokens("a", "r"))

            val afterReinstall = EncryptedTokenStore(file, MemoryCipher())

            assertNull(afterReinstall.load())
            assertFalse(file.exists())
        }
}
