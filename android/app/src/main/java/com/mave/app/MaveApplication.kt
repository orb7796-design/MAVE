package com.mave.app

import android.app.Application
import com.mave.app.data.Network

class MaveApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // The one place the backend URL is wired in (debug: emulator localhost, release: -PMAVE_API_URL, see app/build.gradle.kts).
        Network.configure(BuildConfig.API_BASE_URL)
    }
}
