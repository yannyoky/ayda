package app.ayda.shared

/** The pair of tokens a native app keeps between launches (ADR 0009). */
data class Tokens(
    val accessToken: String,
    val refreshToken: String,
)

/**
 * Where the app keeps its tokens. Android stores them in encrypted storage,
 * iOS in the Keychain; tests use [InMemoryTokenStore].
 */
interface TokenStore {
    suspend fun load(): Tokens?

    suspend fun save(tokens: Tokens)

    suspend fun clear()
}

class InMemoryTokenStore(
    private var tokens: Tokens? = null,
) : TokenStore {
    override suspend fun load(): Tokens? = tokens

    override suspend fun save(tokens: Tokens) {
        this.tokens = tokens
    }

    override suspend fun clear() {
        tokens = null
    }
}
