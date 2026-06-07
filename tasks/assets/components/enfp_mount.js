import Vue from 'vue'
import EnfpDashboard from './EnfpDashboard.vue'
import { autosizeDirective } from '../autosize.js'

import "../app.scss";

Vue.directive('autosize', autosizeDirective)

new Vue({
  render: h => h(EnfpDashboard),
}).$mount('#enfp-app')
