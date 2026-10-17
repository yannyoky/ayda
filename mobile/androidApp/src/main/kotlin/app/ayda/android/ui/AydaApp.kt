package app.ayda.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.ayda.android.R
import app.ayda.android.ui.home.HomeScreen
import app.ayda.android.ui.onboarding.ConsentScreen
import app.ayda.android.ui.onboarding.OnboardingScreen
import app.ayda.android.ui.signin.SignInScreen
import app.ayda.api.models.Theme
import app.ayda.shared.AydaClient
import app.ayda.shared.auth.SignIn
import app.ayda.shared.auth.SignInViewModel
import app.ayda.shared.onboarding.ConsentViewModel
import app.ayda.shared.onboarding.OnboardingViewModel
import app.ayda.shared.session.SessionState
import app.ayda.shared.session.SessionViewModel

/** Picks the top-level screen from the session state. */
@Composable
fun AydaApp(client: AydaClient) {
    val session = viewModel { SessionViewModel(client) }
    val state by session.state.collectAsStateWithLifecycle()
    val theme = (state as? SessionState.SignedIn)?.me?.theme ?: Theme.graphite

    AydaTheme(theme) {
        when (val current = state) {
            SessionState.Loading -> Centered { CircularProgressIndicator(color = LocalAydaColors.current.accent) }
            SessionState.Offline ->
                Centered {
                    Text(stringResource(R.string.offline), style = MaterialTheme.typography.bodyLarge)
                    PrimaryButton(stringResource(R.string.retry), onClick = session::restore)
                }
            SessionState.SignedOut -> {
                val signIn = viewModel { SignInViewModel(SignIn(client), session::onSignedIn) }
                SignInScreen(signIn)
            }
            is SessionState.SignedIn -> {
                val me = current.me
                val consent = me.consentRequired
                when {
                    consent != null -> {
                        val model =
                            viewModel(
                                key = "consent-$consent",
                            ) { ConsentViewModel(client, consent, session::onProfileChanged) }
                        ConsentScreen(model)
                    }
                    !me.onboarded -> {
                        val model =
                            viewModel(
                                key = "onboarding-${me.id}",
                            ) { OnboardingViewModel(client, me, session::onProfileChanged) }
                        OnboardingScreen(model)
                    }
                    else -> HomeScreen(me, onSignOut = session::signOut)
                }
            }
        }
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Box(
        modifier =
            Modifier
                .fillMaxSize()
                .background(LocalAydaColors.current.bg)
                .safeDrawingPadding()
                .padding(16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
            content()
        }
    }
}
