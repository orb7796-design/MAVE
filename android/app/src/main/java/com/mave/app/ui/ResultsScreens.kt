package com.mave.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.mave.app.Paging
import com.mave.app.MaveViewModel
import com.mave.app.data.SearchItem

@Composable
fun ResultsScreen(vm: MaveViewModel, onBack: () -> Unit) {
    val tabs = listOf("ai", "web", "images", "videos", "news", "tech")
    var tab by remember { mutableIntStateOf(0) }
    var text by remember(vm.query) { mutableStateOf(vm.query) }
    val tabKey = tabs[tab]

    LaunchedEffect(vm.query, tabKey) { vm.loadTab(tabKey) }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
            }
            MaveSearchBar(vm, text, { text = it; vm.onTyping(it) }, { vm.runSearch(it) })
        }
        SuggestionList(vm) { text = it; vm.runSearch(it) }
        ScrollableTabRow(selectedTabIndex = tab, edgePadding = 8.dp) {
            tabs.forEachIndexed { idx, k ->
                Tab(selected = tab == idx, onClick = { tab = idx }, text = { Text(L.t(k, vm.lang)) })
            }
        }
        if (vm.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        vm.error?.let {
            Column(Modifier.padding(16.dp)) {
                Text(it, color = MaterialTheme.colorScheme.error)
                TextButton(onClick = { vm.retry(tabKey) }) { Text(L.t("retry", vm.lang)) }
            }
        }
        when (tabKey) {
            "ai" -> AiTab(vm)
            "images" -> ImagesTab(vm, vm.results["images"].orEmpty())
            else -> ListTab(vm, tabKey, vm.results[tabKey].orEmpty())
        }
    }
}

@Composable
fun AiTab(vm: MaveViewModel) {
    val a = vm.aiAnswer ?: return
    val uri = LocalUriHandler.current
    val cited = a.citations.orEmpty()
    val insufficient = a.insufficient == true
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Card(Modifier.fillMaxWidth()) { Text(a.answer, Modifier.padding(16.dp)) }
        }
        // grounded == false: the model wrote an answer without citing any source -> warn instead of presenting it as fact.
        if (!insufficient && a.grounded == false) {
            item {
                Text(
                    L.t("ungrounded_warning", vm.lang),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
        if (!insufficient && (cited.isNotEmpty() || a.sources.isNotEmpty())) {
            item { Text(L.t("sources", vm.lang), style = MaterialTheme.typography.titleMedium) }
        }
        if (!insufficient) {
            if (cited.isNotEmpty()) {
                // Only sources the answer really cites, with the same numbers as the [n] markers in the text.
                items(cited) { c ->
                    Text(
                        "[${c.n}] ${c.title}",
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.clickable { runCatching { uri.openUri(c.url) } }
                    )
                }
            } else {
                itemsIndexed(a.sources) { i, s ->
                    Text(
                        "[${i + 1}] ${s.title}",
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.clickable { runCatching { uri.openUri(s.url) } }
                    )
                }
            }
        }
    }
}

@Composable
fun ListTab(vm: MaveViewModel, tabKey: String, list: List<SearchItem>) {
    if (list.isEmpty() && !vm.loading && vm.error == null && vm.results.containsKey(tabKey)) {
        Text(L.t("no_results", vm.lang), Modifier.padding(16.dp))
    }
    val listState = rememberLazyListState()
    // Near the end of the list (last 4 items) -> ask for the next page. Re-checked whenever the list or footer state changes.
    val nearEnd by remember(listState) {
        derivedStateOf {
            val info = listState.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull()?.index ?: -1
            info.totalItemsCount > 0 && last >= info.totalItemsCount - 4
        }
    }
    val paging = vm.pagingOf(tabKey)
    LaunchedEffect(tabKey, nearEnd, list.size, paging) {
        if (nearEnd && list.isNotEmpty()) vm.loadMore(tabKey)
    }
    LazyColumn(
        state = listState,
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        val dym = vm.didYouMean
        if (tabKey == "web" && dym != null) {
            item {
                TextButton(onClick = { vm.runSearch(dym) }) {
                    Text("${L.t("did_you_mean", vm.lang)} $dym", fontWeight = FontWeight.SemiBold)
                }
            }
        }
        items(list) { item -> ResultCard(vm, item) }
        item { PagingFooter(vm, tabKey) }
    }
}

/** Spinner while the next page loads; a message + retry button if it failed. Nothing otherwise. */
@Composable
fun PagingFooter(vm: MaveViewModel, tabKey: String) {
    when (vm.pagingOf(tabKey)) {
        Paging.LOADING -> Box(Modifier.fillMaxWidth().padding(8.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        Paging.ERROR -> Column(
            Modifier.fillMaxWidth().padding(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(L.t("load_more_failed", vm.lang), color = MaterialTheme.colorScheme.error)
            TextButton(onClick = { vm.retryMore(tabKey) }) { Text(L.t("retry", vm.lang)) }
        }
        else -> Unit
    }
}

@Composable
fun ImagesTab(vm: MaveViewModel, list: List<SearchItem>) {
    val uri = LocalUriHandler.current
    if (list.isEmpty() && !vm.loading && vm.error == null && vm.results.containsKey("images")) {
        Text(L.t("no_results", vm.lang), Modifier.padding(16.dp))
    }
    val gridState = rememberLazyGridState()
    val nearEnd by remember(gridState) {
        derivedStateOf {
            val info = gridState.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull()?.index ?: -1
            info.totalItemsCount > 0 && last >= info.totalItemsCount - 6
        }
    }
    val paging = vm.pagingOf("images")
    LaunchedEffect(nearEnd, list.size, paging) {
        if (nearEnd && list.isNotEmpty()) vm.loadMore("images")
    }
    LazyVerticalGrid(
        state = gridState,
        columns = GridCells.Fixed(2),
        contentPadding = PaddingValues(8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(list) { item ->
            AsyncImage(
                model = item.thumbnail,
                contentDescription = item.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .aspectRatio(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { runCatching { uri.openUri(item.url) } }
            )
        }
        item(span = { GridItemSpan(maxLineSpan) }) { PagingFooter(vm, "images") }
    }
}
