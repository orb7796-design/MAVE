package com.mave.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mave.app.ui.MaveApp
import com.mave.app.ui.MaveTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val vm: MaveViewModel = viewModel()
            MaveTheme(dark = vm.darkMode) {
                MaveApp(vm)
            }
        }
    }
}
