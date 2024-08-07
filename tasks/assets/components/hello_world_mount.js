import Vue from 'vue'
import Vuex from 'vuex'
import VueRouter from 'vue-router'
import HelloWorldComponent from './hello_world.vue'
import Board from './Board.vue'
import Blackboard from './Blackboard.vue'

import store from '../store'

import LiquorTree from '../liquor-tree/src/main.js'

Vue.use(LiquorTree)
Vue.use(Vuex)
Vue.use(VueRouter)

import axios from 'axios'

const routes = [
    { path: '/', component: Board },
    { path: '/board', component: Blackboard },
]

const router = new VueRouter({
    routes
})

new Vue({
    render: h => h(HelloWorldComponent),
    store: new Vuex.Store(store),

    router,

    mounted() {
       this.$store.dispatch('init')
    },

    created() {
       let token = document.body.querySelector('[name=csrfmiddlewaretoken]');
       axios.defaults.headers.common['X-CSRFToken'] = token.value;
    }
}).$mount('#app')
