package com.mave.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.mave.app.MaveViewModel

@Composable
fun SavedScreen(vm: MaveViewModel) {
    Column(Modifier.fillMaxSize().statusBarsPadding().padding(16.dp)) {
        Text(L.t("saved", vm.lang), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        if (vm.saved.isEmpty()) Text(L.t("empty", vm.lang))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(vm.saved.toList()) { item -> ResultCard(vm, item) }
        }
    }
}

@Composable
fun HistoryScreen(vm: MaveViewModel, onSearch: (String) -> Unit) {
    Column(Modifier.fillMaxSize().statusBarsPadding().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                L.t("history", vm.lang),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f)
            )
            if (vm.history.isNotEmpty()) {
                TextButton(onClick = { vm.clearHistory() }) { Text(L.t("clear", vm.lang)) }
            }
        }
        Spacer(Modifier.height(12.dp))
        if (vm.history.isEmpty()) Text(L.t("empty", vm.lang))
        LazyColumn {
            items(vm.history.toList()) { q ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onSearch(q) }
                        .padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(q, Modifier.weight(1f))
                    IconButton(onClick = { vm.removeHistory(q) }) {
                        Icon(Icons.Filled.Delete, contentDescription = "Delete")
                    }
                }
            }
        }
    }
}
