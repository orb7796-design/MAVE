plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// e.g. ./gradlew :app:assembleRelease -PMAVE_API_URL=https://api.yourdomain.org/
val releaseApiUrl: String = (findProperty("MAVE_API_URL") as String?)?.trim()?.let { if (it.endsWith("/")) it else "$it/" }.orEmpty()

tasks.matching { it.name.matches(Regex("(assemble|bundle|package)Release.*")) }.configureEach {
    doFirst {
        require(releaseApiUrl.startsWith("https://") && !releaseApiUrl.contains("example")) {
            "Set MAVE_API_URL to your real HTTPS backend (e.g. -PMAVE_API_URL=https://api.yourdomain.org/) before building a release."
        }
    }
}

android {
    namespace = "com.mave.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.mave.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 3
        versionName = "0.4.0"
    }

    buildTypes {
        debug {
            // Android emulator -> your PC's localhost (cleartext allowed only in debug, see src/debug)
            buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/\"")
        }
        release {
            // Real backend URL comes from -PMAVE_API_URL=https://... or android/gradle.properties (never hard-coded);
            // release tasks fail below if it is missing or not HTTPS.
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.00")
    implementation(composeBom)
    implementation(project(":data")) // network, storage, API models (retrofit comes through it as `api`)
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.5")
    implementation("androidx.navigation:navigation-compose:2.8.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
