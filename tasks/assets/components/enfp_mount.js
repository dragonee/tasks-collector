import Vue from 'vue'
import EnfpDashboard from './EnfpDashboard.vue'

import "../app.scss";

new Vue({
  render: h => h(EnfpDashboard),
}).$mount('#enfp-app')
