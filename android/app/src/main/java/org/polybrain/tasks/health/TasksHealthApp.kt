package org.polybrain.tasks.health

import android.app.Application
import org.polybrain.tasks.health.data.Settings

class TasksHealthApp : Application() {

    val settings: Settings by lazy { Settings(applicationContext) }
}
