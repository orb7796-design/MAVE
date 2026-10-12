package com.mave.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mave.app.MaveViewModel

@Composable
fun ProfileScreen(vm: MaveViewModel, onLogin: () -> Unit, onSettings: () -> Unit) {
    Column(Modifier.fillMaxSize().statusBarsPadding().padding(24.dp)) {
        Text(L.t("profile", vm.lang), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))
        val u = vm.user
        if (u != null) {
            Text("${L.t("signed_in_as", vm.lang)}: $u")
            Spacer(Modifier.height(12.dp))
            OutlinedButton(onClick = { vm.logout() }) { Text(L.t("logout", vm.lang)) }
        } else {
            Text(L.t("guest_name", vm.lang))
            Spacer(Modifier.height(12.dp))
            Button(onClick = onLogin) { Text(L.t("login", vm.lang)) }
        }
        Spacer(Modifier.height(12.dp))
        TextButton(onClick = onSettings) { Text(L.t("settings", vm.lang)) }
    }
}

@Composable
fun SettingsScreen(vm: MaveViewModel, onBack: () -> Unit) {
    Column(Modifier.fillMaxSize().statusBarsPadding().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
            }
            Text(L.t("settings", vm.lang), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(L.t("dark_mode", vm.lang), Modifier.weight(1f))
            Switch(checked = vm.darkMode, onCheckedChange = { vm.setDark(it) })
        }
        Spacer(Modifier.height(16.dp))
        Text(L.t("language", vm.lang), style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = vm.lang == "om", onClick = { vm.updateLang("om") }, label = { Text("Afaan Oromoo") })
            FilterChip(selected = vm.lang == "en", onClick = { vm.updateLang("en") }, label = { Text("English") })
        }
    }
}
