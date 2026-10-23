package app.ayda.android.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.ayda.android.R
import app.ayda.android.push.Push
import app.ayda.android.ui.assistant.AssistantScreen
import app.ayda.android.ui.chat.ChatScreen
import app.ayda.android.ui.chat.ChatsScreen
import app.ayda.android.ui.chat.MeetupSheet
import app.ayda.android.ui.coop.CoopScreen
import app.ayda.android.ui.coop.CoopSheet
import app.ayda.android.ui.day.CompleteScreen
import app.ayda.android.ui.day.PickScreen
import app.ayda.android.ui.day.TodayScreen
import app.ayda.android.ui.onboarding.ConsentScreen
import app.ayda.android.ui.onboarding.OnboardingScreen
import app.ayda.android.ui.profile.ProfileScreen
import app.ayda.android.ui.recipes.RecipeSheet
import app.ayda.android.ui.signin.SignInScreen
import app.ayda.android.ui.social.FeedScreen
import app.ayda.android.ui.social.FriendsScreen
import app.ayda.android.ui.social.InviteDialog
import app.ayda.api.models.DayQuest
import app.ayda.api.models.Me
import app.ayda.api.models.Theme
import app.ayda.shared.AydaClient
import app.ayda.shared.assistant.AssistantViewModel
import app.ayda.shared.auth.SignIn
import app.ayda.shared.auth.SignInViewModel
import app.ayda.shared.chat.ChatViewModel
import app.ayda.shared.chat.ChatsViewModel
import app.ayda.shared.coop.CoopInviteViewModel
import app.ayda.shared.coop.CoopViewModel
import app.ayda.shared.coop.CoopsViewModel
import app.ayda.shared.day.CompleteViewModel
import app.ayda.shared.day.TodayViewModel
import app.ayda.shared.onboarding.ConsentViewModel
import app.ayda.shared.onboarding.OnboardingViewModel
import app.ayda.shared.plans.MeetupViewModel
import app.ayda.shared.profile.ProfileViewModel
import app.ayda.shared.push.PushRegistration
import app.ayda.shared.push.PushTarget
import app.ayda.shared.realtime.CentrifugeTransport
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.recipes.RecipesViewModel
import app.ayda.shared.session.SessionState
import app.ayda.shared.session.SessionViewModel
import app.ayda.shared.social.FeedViewModel
import app.ayda.shared.social.FriendsViewModel
import app.ayda.shared.social.InviteViewModel
import kotlinx.coroutines.flow.StateFlow

/** Picks the top-level screen from the session state. */
@Composable
fun AydaApp(
    client: AydaClient,
    push: PushRegistration,
    opened: StateFlow<PushTarget?>,
    onOpened: () -> Unit,
) {
    val session = viewModel { SessionViewModel(client, beforeSignOut = push::unregister) }
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
                    else -> SignedInHome(client, me, session, push, opened, onOpened)
                }
            }
        }
    }
}

private enum class Screen { Today, Feed, Chats, Friends, Profile, Pick, Complete, Chat, Coop, Assistant }

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
    push: PushRegistration,
    opened: StateFlow<PushTarget?>,
    onOpened: () -> Unit,
) {
    var screen by rememberSaveable { mutableStateOf(Screen.Today) }
    var completing by rememberSaveable { mutableStateOf<String?>(null) }
    var chatId by rememberSaveable { mutableStateOf<String?>(null) }
    var chatFrom by rememberSaveable { mutableStateOf(Screen.Chats) }
    var coopId by rememberSaveable { mutableStateOf<String?>(null) }
    var inviting by rememberSaveable { mutableStateOf<String?>(null) }
    var cooking by rememberSaveable { mutableStateOf(false) }
    var assistantQuest by rememberSaveable { mutableStateOf<String?>(null) }
    var assistantFrom by rememberSaveable { mutableStateOf(Screen.Today) }
    var assistantRecipe by rememberSaveable { mutableStateOf<String?>(null) }
    var meetupChat by rememberSaveable { mutableStateOf<String?>(null) }
    var invitedBy by rememberSaveable { mutableStateOf<String?>(null) }
    // A new friend through a link: the friends list is loaded again.
    var friendsRev by rememberSaveable { mutableIntStateOf(0) }
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
    val coops = viewModel(key = "coops-${me.id}") { CoopsViewModel(client, realtime, today::refresh) }
    val openCoop = { id: String ->
        coopId = id
        screen = Screen.Coop
    }
    val complete = { quest: DayQuest ->
        completing = quest.id
        screen = Screen.Complete
    }
    val openChat = { id: String ->
        chatFrom = if (screen == Screen.Chat) chatFrom else screen
        chatId = id
        screen = Screen.Chat
    }
    val openAssistant = { quest: DayQuest? ->
        assistantFrom = if (screen == Screen.Assistant) assistantFrom else screen
        assistantQuest = quest?.id
        screen = Screen.Assistant
    }
    val back = {
        today.dismissNotice()
        screen =
            when (screen) {
                Screen.Chat -> chatFrom
                Screen.Assistant -> assistantFrom
                else -> Screen.Today
            }
    }
    if (screen != Screen.Today) BackHandler(onBack = back)
    PushSetup(me, push)
    val target by opened.collectAsStateWithLifecycle()
    LaunchedEffect(target) {
        when (val to = target ?: return@LaunchedEffect) {
            PushTarget.Today -> screen = Screen.Today
            PushTarget.Feed -> screen = Screen.Feed
            PushTarget.Friends -> screen = Screen.Friends
            is PushTarget.Chat -> openChat(to.conversationId)
            is PushTarget.Coop -> openCoop(to.coopId)
            is PushTarget.Invite -> invitedBy = to.code
        }
        onOpened()
    }

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
                        coops,
                        onPick = { screen = Screen.Pick },
                        onComplete = complete,
                        onOpenCoop = openCoop,
                        onInviteCoop = { inviting = it.id },
                        onCook = { cooking = true },
                        onAssistant = openAssistant,
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
                        ChatScreen(model, me.id, onBack = back, onMeetup = { meetupChat = id })
                    }
                }
                Screen.Coop -> {
                    val id = coopId
                    if (id == null) {
                        LaunchedEffect(Unit) { back() }
                    } else {
                        val model =
                            viewModel(viewModelStoreOwner = rememberScreenStore("coop-$id")) {
                                CoopViewModel(client, realtime, id) {
                                    coops.updated(it)
                                    today.refresh()
                                }
                            }
                        val coop by model.state.collectAsStateWithLifecycle()
                        val myQuestId = coop.coop?.myQuestId
                        CoopScreen(
                            model,
                            me.id,
                            myQuest = todayState.day?.quests?.firstOrNull { it.id == myQuestId },
                            quests = todayState.day?.quests.orEmpty(),
                            onBack = back,
                            onComplete = complete,
                            onChat = openChat,
                        )
                    }
                }
                Screen.Friends -> {
                    val model = viewModel(key = "friends-${me.id}-$friendsRev") { FriendsViewModel(client) }
                    FriendsScreen(model, onWrite = { friend -> chats.openDirect(friend.id) { openChat(it.id) } })
                }
                Screen.Profile -> {
                    val model =
                        viewModel(key = "profile-${me.id}") {
                            ProfileViewModel(client, me, session::onProfileChanged, session::signOut)
                        }
                    ProfileScreen(model)
                }
                Screen.Pick -> PickScreen(today, onClose = back, onDiscuss = openAssistant)
                Screen.Assistant -> {
                    val questId = assistantQuest
                    val quests = todayState.day?.quests.orEmpty()
                    // Each topic keeps its own history while the app is open
                    val model =
                        viewModel(viewModelStoreOwner = rememberScreenStore("assistant-${questId ?: "day"}")) {
                            AssistantViewModel(client, questId, today::refresh)
                        }
                    AssistantScreen(
                        model,
                        quest = quests.firstOrNull { it.id == questId },
                        questStates = quests.associate { it.id to it.state },
                        onBack = back,
                        onCook = { assistantRecipe = it },
                    )
                }
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
        val invitingQuest = todayState.day?.quests?.firstOrNull { it.id == inviting }
        if (invitingQuest != null) {
            val model =
                viewModel(viewModelStoreOwner = rememberScreenStore("invite-${invitingQuest.id}")) {
                    CoopInviteViewModel(client, invitingQuest.id)
                }
            CoopSheet(model, invitingQuest, onClose = { inviting = null }) { coop ->
                inviting = null
                coops.updated(coop)
                today.refresh()
                openCoop(coop.id)
            }
        }
        if (cooking) {
            val model = viewModel(viewModelStoreOwner = rememberScreenStore("recipes")) { RecipesViewModel(client) }
            RecipeSheet(model, onClose = { cooking = false }) { coop ->
                cooking = false
                coops.updated(coop)
                today.refresh()
                openCoop(coop.id)
            }
        }
        assistantRecipe?.let { id ->
            val model =
                viewModel(viewModelStoreOwner = rememberScreenStore("recipe-$id")) {
                    RecipesViewModel(client).also { it.choose(id) }
                }
            RecipeSheet(model, onClose = { assistantRecipe = null }) { coop ->
                assistantRecipe = null
                coops.updated(coop)
                today.refresh()
                openCoop(coop.id)
            }
        }
        meetupChat?.let { id ->
            val model =
                viewModel(viewModelStoreOwner = rememberScreenStore("meetup-$id")) { MeetupViewModel(client, id) }
            MeetupSheet(model, onClose = { meetupChat = null }) { coop ->
                meetupChat = null
                coops.updated(coop)
                today.refresh()
                openCoop(coop.id)
            }
        }
        invitedBy?.let { code ->
            val model = viewModel(key = "invite-link-$code") { InviteViewModel(client, code) }
            InviteDialog(model, onClose = { invitedBy = null }) {
                invitedBy = null
                friendsRev++
                screen = Screen.Friends
            }
        }
        if (tab != null) TabBar(tab, unreadChats = chatsState.unread, onSelect = { screen = it.screen() })
    }
}

/** Asks for the notification permission once and registers this phone's push token. */
@Composable
private fun PushSetup(
    me: Me,
    push: PushRegistration,
) {
    val context = LocalContext.current
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(me.id) {
        if (!Push.enabled) return@LaunchedEffect
        val needed =
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
        if (needed) ask.launch(Manifest.permission.POST_NOTIFICATIONS)
        Push.token()?.let { push.register(it) }
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
