import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Per-developer overrides for debug builds — pointing the emulator at a
// local Django server and pre-filling an API token so the Settings
// screen doesn't have to be re-entered on every install. Lookup order:
//   1. android/local.properties  (gitignored)
//   2. environment variable
// Empty when neither is set; the app then behaves exactly like a fresh
// install and the user types values into Settings as usual.
val devProperties: Properties = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

fun devString(localKey: String, envKey: String): String =
    devProperties.getProperty(localKey) ?: System.getenv(envKey) ?: ""

fun escapeForBuildConfig(raw: String): String =
    raw.replace("\\", "\\\\").replace("\"", "\\\"")

fun quotedBuildConfig(raw: String): String = "\"" + escapeForBuildConfig(raw) + "\""

android {
    namespace = "org.polybrain.tasks.health"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "org.polybrain.tasks.health"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = libs.versions.versionCode.get().toInt()
        versionName = libs.versions.versionName.get()

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            // Release never carries dev defaults — Settings UI is the
            // only source of server URL / token in user builds.
            buildConfigField("String", "DEV_SERVER_URL", "\"\"")
            buildConfigField("String", "DEV_API_TOKEN", "\"\"")
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField(
                "String",
                "DEV_SERVER_URL",
                quotedBuildConfig(
                    devString("tasks.devServerUrl", "TASKS_DEV_SERVER_URL")
                ),
            )
            buildConfigField(
                "String",
                "DEV_API_TOKEN",
                quotedBuildConfig(
                    devString("tasks.devApiToken", "TASKS_DEV_API_TOKEN")
                ),
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    debugImplementation(libs.androidx.compose.ui.tooling)

    implementation(libs.androidx.health.connect)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.play.services.location)

    implementation(libs.retrofit.core)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
