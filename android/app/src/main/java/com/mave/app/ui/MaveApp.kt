package com.mave.app.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.mave.app.MaveViewModel

private data class BottomItem(val route: String, val labelKey: String, val icon: ImageVector)

@Composable
fun MaveApp(vm: MaveViewModel) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route

    val bottomItems = listOf(
        BottomItem("home", "home", Icons.Filled.Home),
        BottomItem("saved", "saved", Icons.Filled.Bookmark),
        BottomItem("history", "history", Icons.Filled.History),
        BottomItem("profile", "profile", Icons.Filled.Person)
    )

    fun search(q: String) {
        vm.runSearch(q)
        if (vm.query.isNotEmpty()) {
            nav.navigate("results") { launchSingleTop = true }
        }
    }

    Surface(Modifier.fillMaxSize()) {
        Scaffold(
            bottomBar = {
                if (bottomItems.any { it.route == route }) {
                    NavigationBar {
                        bottomItems.forEach { item ->
                            NavigationBarItem(
                                selected = route == item.route,
                                onClick = {
                                    nav.navigate(item.route) {
                                        popUpTo("home") { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                },
                                icon = { Icon(item.icon, contentDescription = null) },
                                label = { Text(L.t(item.labelKey, vm.lang)) }
                            )
                        }
                    }
                }
            }
        ) { pad ->
            NavHost(nav, startDestination = "splash", modifier = Modifier.padding(pad)) {
                composable("splash") {
                    SplashScreen(vm) {
                        nav.navigate(if (vm.onboarded) "home" else "onboarding") {
                            popUpTo("splash") { inclusive = true }
                        }
                    }
                }
                composable("onboarding") {
                    OnboardingScreen(vm) {
                        nav.navigate("auth") { popUpTo("onboarding") { inclusive = true } }
                    }
                }
                composable("auth") {
                    AuthScreen(vm) {
                        vm.markOnboarded()
                        nav.navigate("home") {
                            popUpTo("home") { inclusive = true }
                            launchSingleTop = true
                        }
                    }
                }
                composable("home") { HomeScreen(vm) { search(it) } }
                composable("results") { ResultsScreen(vm) { nav.popBackStack() } }
                composable("saved") { SavedScreen(vm) }
                composable("history") { HistoryScreen(vm) { search(it) } }
                composable("profile") {
                    ProfileScreen(vm, onLogin = { nav.navigate("auth") }, onSettings = { nav.navigate("settings") })
                }
                composable("settings") { SettingsScreen(vm) { nav.popBackStack() } }
            }
        }
    }
}
