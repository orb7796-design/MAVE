plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

// Network + persistence + API models. No UI, no Compose. The app module owns the base URL and passes it in with
// Network.configure(...), so there is exactly one place (app/build.gradle.kts) that decides debug vs release URLs.
android {
    namespace = "com.mave.app.data"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }
    buildTypes {
        release {
            isMinifyEnabled = false // R8 runs once, in :app
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // retrofit is `api`: callers catch retrofit2.HttpException, which is part of this module's error contract.
    api("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
