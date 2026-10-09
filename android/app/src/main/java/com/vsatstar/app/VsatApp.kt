package com.vsatstar.app

import android.app.Application

class VsatApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Prefs.init(this)
        Notifier.createChannels(this)
        Vsat.init(this)
    }
}
