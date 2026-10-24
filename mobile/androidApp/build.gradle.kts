import java.net.URI

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "app.ayda.android"
    compileSdk = 37

    defaultConfig {
        applicationId = "app.ayda"
        minSdk = 26
        targetSdk = 37
        // The release workflow passes -Payda.versionCode=<run number> -Payda.versionName=<tag>.
        versionCode = providers.gradleProperty("ayda.versionCode").map { it.toInt() }.getOrElse(1)
        versionName = providers.gradleProperty("ayda.versionName").getOrElse("0.1.0")
        // Where the API lives; override with -Payda.apiBaseUrl=... (the emulator reaches the host at 10.0.2.2).
        val apiBaseUrl = providers.gradleProperty("ayda.apiBaseUrl").orElse("http://10.0.2.2:8000/api/v1")
        buildConfigField("String", "API_BASE_URL", "\"${apiBaseUrl.get()}\"")
        // Invite links https://<host>/i/<code> open the app (Android App Links); the host is the API's.
        val inviteHost = URI(apiBaseUrl.get()).host
        buildConfigField("String", "INVITE_HOST", "\"$inviteHost\"")
        manifestPlaceholders["inviteHost"] = inviteHost
        // Crash reports go to the self-hosted GlitchTip (a Sentry DSN); empty: reporting is off.
        val sentryDsn =
            providers
                .gradleProperty(
                    "ayda.sentryDsn",
                ).orElse(providers.environmentVariable("AYDA_SENTRY_DSN"))
        buildConfigField("String", "SENTRY_DSN", "\"${sentryDsn.getOrElse("")}\"")
        // The Firebase project for push (ADR 0009), from -Payda.firebase.*=... or AYDA_FIREBASE_* variables.
        // Left empty, the app builds and runs without push.
        listOf("appId", "projectId", "apiKey", "senderId").forEach { name ->
            val constant = "FIREBASE_" + name.replace(Regex("([A-Z])"), "_$1").uppercase()
            val value =
                providers
                    .gradleProperty(
                        "ayda.firebase.$name",
                    ).orElse(providers.environmentVariable("AYDA_$constant"))
            buildConfigField("String", constant, "\"${value.getOrElse("")}\"")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // The release keystore lives in GitHub secrets (.github/workflows/android-release.yml); without
    // it the release build is left unsigned.
    val keystore = providers.environmentVariable("AYDA_KEYSTORE_FILE")
    signingConfigs {
        if (keystore.isPresent) {
            create("release") {
                storeFile = file(keystore.get())
                storePassword = providers.environmentVariable("AYDA_KEYSTORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("AYDA_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("AYDA_KEY_PASSWORD").get()
            }
        }
    }

    buildTypes {
        release {
            if (keystore.isPresent) signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    lint {
        warningsAsErrors = true
        // New library or SDK releases must not turn CI red on their own.
        disable += setOf("GradleDependency", "NewerVersionAvailable", "OldTargetApi", "AndroidGradlePluginVersion")
        abortOnError = true
    }
}

dependencies {
    implementation(project(":shared"))
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.activity.compose)
    implementation(libs.core.ktx)
    implementation(libs.exifinterface)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime.compose)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.messaging)
    implementation(libs.sentry.android)
    // Video circles in chats (ADR 0019): the front camera, recorded at SD quality.
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.video)
    implementation(libs.camera.view)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
