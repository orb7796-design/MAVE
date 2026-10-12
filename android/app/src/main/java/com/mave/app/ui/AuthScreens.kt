package com.mave.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mave.app.MaveViewModel

@Composable
fun AuthScreen(vm: MaveViewModel, onDone: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var register by remember { mutableStateOf(false) }
    var showReset by remember { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            "MAVE",
            fontSize = 40.sp,
            fontWeight = FontWeight.Black,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text(L.t("email", vm.lang)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text(L.t("password", vm.lang)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth()
        )
        vm.authError?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.authenticate(email, password, register, onDone) },
            modifier = Modifier.fillMaxWidth()
        ) { Text(L.t(if (register) "signup" else "login", vm.lang)) }
        TextButton(onClick = { register = !register }) {
            Text(L.t(if (register) "login" else "signup", vm.lang))
        }
        if (!register) {
            TextButton(onClick = { vm.clearResetInfo(); showReset = true }) { Text(L.t("forgot_pw", vm.lang)) }
        }
        TextButton(onClick = onDone) { Text(L.t("guest", vm.lang)) }
    }
    if (showReset) ResetPasswordDialog(vm, email) { showReset = false }
}

/** Step 1: e-mail -> server mails a code. Step 2: code + new password. Step 3: done. */
@Composable
fun ResetPasswordDialog(vm: MaveViewModel, initialEmail: String, onClose: () -> Unit) {
    var email by remember { mutableStateOf(initialEmail) }
    var code by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var step by remember { mutableIntStateOf(1) }
    AlertDialog(
        onDismissRequest = { vm.clearResetInfo(); onClose() },
        title = { Text(L.t("reset_title", vm.lang)) },
        text = {
            Column {
                when (step) {
                    1 -> OutlinedTextField(
                        value = email,
                        onValueChange = { email = it },
                        label = { Text(L.t("email", vm.lang)) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        modifier = Modifier.fillMaxWidth()
                    )
                    2 -> Column {
                        Text(L.t("reset_sent", vm.lang))
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(
                            value = code,
                            onValueChange = { code = it },
                            label = { Text(L.t("code", vm.lang)) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(
                            value = password,
                            onValueChange = { password = it },
                            label = { Text(L.t("new_password", vm.lang)) },
                            singleLine = true,
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    else -> Text(L.t("reset_done", vm.lang))
                }
                vm.resetInfo?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                when (step) {
                    1 -> vm.requestReset(email) { step = 2 }
                    2 -> vm.completeReset(code, password) { step = 3 }
                    else -> { vm.clearResetInfo(); onClose() }
                }
            }) { Text(L.t(when (step) { 1 -> "send_code"; 2 -> "reset_btn"; else -> "ok" }, vm.lang)) }
        },
        dismissButton = {
            if (step < 3) {
                TextButton(onClick = { vm.clearResetInfo(); onClose() }) { Text(L.t("cancel", vm.lang)) }
            }
        }
    )
}
