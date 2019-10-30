import Vue from 'vue'
import HelloWorldComponent from './hello_world.vue'

new Vue({
   render: h => h(HelloWorldComponent)
}).$mount('#app')
