package com.dragonee.tasks.health

import android.app.Application
import com.dragonee.tasks.health.data.Settings

class TasksHealthApp : Application() {

    val settings: Settings by lazy { Settings(applicationContext) }
}
