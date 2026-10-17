import org.openapitools.generator.gradle.plugin.tasks.GenerateTask

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.android.kmp.library)
    alias(libs.plugins.openapi.generator)
}

val contract = rootProject.layout.projectDirectory.file("../contracts/openapi.yaml")
val generatedClient = layout.buildDirectory.dir("generated/openapi")

// The API client is generated from the contract on every build (ADR 0004, ADR 0009),
// so a contract change that breaks the app fails compilation here.
val generateApiClient =
    tasks.register<GenerateTask>("generateApiClient") {
        generatorName.set("kotlin")
        library.set("multiplatform")
        inputSpec.set(contract.asFile.path)
        // inputSpec is only a path string; track the file itself so contract edits regenerate the client.
        inputs.file(contract).withPathSensitivity(PathSensitivity.RELATIVE)
        outputDir.set(generatedClient)
        // Drop files of schemas that left the contract.
        cleanupOutput.set(true)
        packageName.set("app.ayda.api")
        generateApiTests.set(false)
        generateModelTests.set(false)
        generateApiDocumentation.set(false)
        generateModelDocumentation.set(false)
        configOptions.set(
            mapOf(
                "dateLibrary" to "kotlinx-datetime",
                "sourceFolder" to "src/commonMain/kotlin",
            ),
        )
        // Only the Kotlin sources; we build them with this module's own Gradle setup.
        globalProperties.set(mapOf("apis" to "", "models" to "", "supportingFiles" to ""))
    }

kotlin {
    android {
        namespace = "app.ayda.shared"
        compileSdk = 37
        minSdk = 26
        withHostTest {}
    }
    listOf(iosArm64(), iosSimulatorArm64()).forEach { target ->
        target.binaries.framework {
            baseName = "Shared"
            isStatic = true
        }
    }

    sourceSets {
        commonMain {
            kotlin.srcDir(generateApiClient.map { generatedClient.get().dir("src/commonMain/kotlin") })
            dependencies {
                implementation(libs.kotlinx.coroutines.core)
                implementation(libs.kotlinx.serialization.json)
                api(libs.kotlinx.datetime)
                api(libs.ktor.client.core)
                implementation(libs.ktor.client.auth)
                implementation(libs.ktor.client.content.negotiation)
                implementation(libs.ktor.serialization.kotlinx.json)
            }
        }
        commonTest {
            dependencies {
                implementation(kotlin("test"))
                implementation(libs.kotlinx.coroutines.test)
                implementation(libs.ktor.client.mock)
            }
        }
        androidMain {
            dependencies {
                implementation(libs.ktor.client.okhttp)
            }
        }
        iosMain {
            dependencies {
                implementation(libs.ktor.client.darwin)
            }
        }
    }
}

// AGP also scans the generated source root for baseline profiles.
tasks.matching { it.name == "prepareAndroidMainArtProfile" }.configureEach { dependsOn(generateApiClient) }
