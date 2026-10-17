package app.ayda.android.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.ayda.android.R
import app.ayda.android.ui.chat.ChatScreen
import app.ayda.android.ui.chat.ChatsScreen
import app.ayda.android.ui.day.CompleteScreen
import app.ayda.android.ui.day.PickScreen
import app.ayda.android.ui.day.TodayScreen
import app.ayda.android.ui.onboarding.ConsentScreen
import app.ayda.android.ui.onboarding.OnboardingScreen
import app.ayda.android.ui.profile.ProfileScreen
import app.ayda.android.ui.signin.SignInScreen
import app.ayda.android.ui.social.FeedScreen
import app.ayda.android.ui.social.FriendsScreen
import app.ayda.api.models.Me
import app.ayda.api.models.Theme
import app.ayda.shared.AydaClient
import app.ayda.shared.auth.SignIn
import app.ayda.shared.auth.SignInViewModel
import app.ayda.shared.chat.ChatViewModel
import app.ayda.shared.chat.ChatsViewModel
import app.ayda.shared.day.CompleteViewModel
import app.ayda.shared.day.TodayViewModel
import app.ayda.shared.onboarding.ConsentViewModel
import app.ayda.shared.onboarding.OnboardingViewModel
import app.ayda.shared.profile.ProfileViewModel
import app.ayda.shared.realtime.CentrifugeTransport
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.session.SessionState
import app.ayda.shared.session.SessionViewModel
import app.ayda.shared.social.FeedViewModel
import app.ayda.shared.social.FriendsViewModel

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
                    else -> SignedInHome(client, me, session)
                }
            }
        }
    }
}

private enum class Screen { Today, Feed, Chats, Friends, Profile, Pick, Complete, Chat }

private fun Screen.tab(): Tab? =
    when (this) {
        Screen.Today -> Tab.Today
        Screen.Feed -> Tab.Feed
        Screen.Chats -> Tab.Chats
        Screen.Friends -> Tab.Friends
        Screen.Profile -> Tab.Profile
        else -> null
    }

private fun Tab.screen(): Screen =
    when (this) {
        Tab.Today -> Screen.Today
        Tab.Feed -> Screen.Feed
        Tab.Chats -> Screen.Chats
        Tab.Friends -> Screen.Friends
        Tab.Profile -> Screen.Profile
    }

@Composable
private fun SignedInHome(
    client: AydaClient,
    me: Me,
    session: SessionViewModel,
) {
    var screen by rememberSaveable { mutableStateOf(Screen.Today) }
    var completing by rememberSaveable { mutableStateOf<String?>(null) }
    var chatId by rememberSaveable { mutableStateOf<String?>(null) }
    var chatFrom by rememberSaveable { mutableStateOf(Screen.Chats) }
    val today = viewModel(key = "today-${me.id}") { TodayViewModel(client) }
    val todayState by today.state.collectAsStateWithLifecycle()
    val realtime = viewModel(key = "realtime-${me.id}") { Realtime(client, CentrifugeTransport()) }
    // No connection in the background: Centrifugo recovers what was missed on return.
    LifecycleStartEffect(realtime) {
        realtime.resume()
        onStopOrDispose { realtime.pause() }
    }
    val chats = viewModel(key = "chats-${me.id}") { ChatsViewModel(client, realtime) }
    val chatsState by chats.state.collectAsStateWithLifecycle()
    val openChat = { id: String ->
        chatFrom = if (screen == Screen.Chat) chatFrom else screen
        chatId = id
        screen = Screen.Chat
    }
    val back = {
        today.dismissNotice()
        screen = if (screen == Screen.Chat) chatFrom else Screen.Today
    }
    if (screen != Screen.Today) BackHandler(onBack = back)

    val tab = screen.tab()
    Column(Modifier.fillMaxSize().background(LocalAydaColors.current.bg)) {
        // The tab bar takes the navigation bar inset, so the screen above must not add it again.
        Box(
            Modifier.weight(1f).then(
                if (tab != null) Modifier.consumeWindowInsets(WindowInsets.navigationBars) else Modifier,
            ),
        ) {
            when (screen) {
                Screen.Today ->
                    TodayScreen(
                        today,
                        me,
                        onPick = { screen = Screen.Pick },
                        onComplete = { quest ->
                            completing = quest.id
                            screen = Screen.Complete
                        },
                    )
                Screen.Feed -> {
                    val model = viewModel(key = "feed-${me.id}") { FeedViewModel(client) }
                    FeedScreen(model, me, contentPadding = PaddingValues(16.dp))
                }
                Screen.Chats -> ChatsScreen(chats, me.id, onOpen = openChat)
                Screen.Chat -> {
                    val id = chatId
                    if (id == null) {
                        LaunchedEffect(Unit) { back() }
                    } else {
                        // Polling and live updates for a chat stop as soon as it is closed.
                        val model =
                            viewModel(viewModelStoreOwner = rememberScreenStore(id)) {
                                ChatViewModel(client, realtime, id, chats::markedRead)
                            }
                        ChatScreen(model, me.id, onBack = back)
                    }
                }
                Screen.Friends -> {
                    val model = viewModel(key = "friends-${me.id}") { FriendsViewModel(client) }
                    FriendsScreen(model, onWrite = { friend -> chats.openDirect(friend.id) { openChat(it.id) } })
                }
                Screen.Profile -> {
                    val model =
                        viewModel(key = "profile-${me.id}") {
                            ProfileViewModel(client, me, session::onProfileChanged, session::signOut)
                        }
                    ProfileScreen(model)
                }
                Screen.Pick -> PickScreen(today, onClose = back)
                Screen.Complete -> {
                    val day = todayState.day
                    val quest = day?.quests?.firstOrNull { it.id == completing }
                    if (day == null || quest == null) {
                        LaunchedEffect(Unit) { back() }
                    } else {
                        val model =
                            viewModel(key = "complete-${quest.id}") {
                                CompleteViewModel(client, quest, day, today::refresh)
                            }
                        CompleteScreen(model, onClose = back)
                    }
                }
            }
        }
        if (tab != null) TabBar(tab, unreadChats = chatsState.unread, onSelect = { screen = it.screen() })
    }
}

/** A view model store that lives while the screen is shown, so its view models stop when it closes. */
@Composable
private fun rememberScreenStore(key: String): ViewModelStoreOwner {
    val owner =
        remember(key) {
            object : ViewModelStoreOwner {
                override val viewModelStore = ViewModelStore()
            }
        }
    DisposableEffect(owner) { onDispose { owner.viewModelStore.clear() } }
    return owner
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
