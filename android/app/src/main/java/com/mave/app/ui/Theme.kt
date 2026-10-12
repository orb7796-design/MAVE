package com.mave.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF2F5BFF),
    secondary = Color(0xFF00A88F),
    background = Color(0xFFFAFAFD),
    surface = Color(0xFFFFFFFF)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FA8FF),
    secondary = Color(0xFF4FD6BE),
    background = Color(0xFF101114),
    surface = Color(0xFF181A1F)
)

@Composable
fun MaveTheme(dark: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, content = content)
}
