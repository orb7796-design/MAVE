package com.mave.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mave.app.MaveViewModel
import kotlinx.coroutines.delay

@Composable
fun SplashScreen(vm: MaveViewModel, onDone: () -> Unit) {
    LaunchedEffect(vm.loaded) {
        if (vm.loaded) {
            delay(900)
            onDone()
        }
    }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                "MAVE",
                fontSize = 52.sp,
                fontWeight = FontWeight.Black,
                color = MaterialTheme.colorScheme.primary
            )
            Text("AI Search", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun OnboardingScreen(vm: MaveViewModel, onDone: () -> Unit) {
    val pages = listOf("ob1", "ob2", "ob3")
    var i by remember { mutableIntStateOf(0) }
    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = vm.lang == "om", onClick = { vm.updateLang("om") }, label = { Text("Afaan Oromoo") })
            FilterChip(selected = vm.lang == "en", onClick = { vm.updateLang("en") }, label = { Text("English") })
        }
        Spacer(Modifier.height(32.dp))
        Text(
            L.t("${pages[i]}_t", vm.lang),
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(16.dp))
        Text(L.t("${pages[i]}_d", vm.lang), textAlign = TextAlign.Center)
        Spacer(Modifier.height(32.dp))
        Button(onClick = { if (i < pages.lastIndex) i++ else onDone() }) {
            Text(L.t(if (i < pages.lastIndex) "next" else "start", vm.lang))
        }
        TextButton(onClick = onDone) { Text(L.t("skip", vm.lang)) }
    }
}
