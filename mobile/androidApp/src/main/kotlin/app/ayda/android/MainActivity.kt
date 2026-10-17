package app.ayda.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import app.ayda.android.ui.AydaTheme
import app.ayda.android.ui.WelcomeScreen
import app.ayda.api.models.Theme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            var theme by rememberSaveable { mutableStateOf(Theme.graphite) }
            AydaTheme(theme) {
                WelcomeScreen(theme = theme, onThemeChange = { theme = it })
            }
        }
    }
}
