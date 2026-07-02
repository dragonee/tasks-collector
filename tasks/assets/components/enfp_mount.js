import { createApp } from 'vue'
import EnfpDashboard from './EnfpDashboard.vue'
import { autosizeDirective } from '../autosize.js'

import "../app.scss";

const app = createApp(EnfpDashboard)

app.directive('autosize', autosizeDirective)

app.mount('#enfp-app')
