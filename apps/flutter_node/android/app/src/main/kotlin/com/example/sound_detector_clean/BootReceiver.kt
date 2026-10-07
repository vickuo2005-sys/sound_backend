package com.example.sound_detector_clean

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return

        if (
            action != Intent.ACTION_BOOT_COMPLETED &&
                action != Intent.ACTION_LOCKED_BOOT_COMPLETED
        ) {
            return
        }

        try {
            val launchIntent = Intent(context, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
                putExtra("started_from_boot", true)
            }

            context.startActivity(launchIntent)
        } catch (_: Exception) {
            // Android 10+ or vendor power managers may block background activity launch.
        }
    }
}
