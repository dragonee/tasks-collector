import Vue from 'vue'
import Vuex from 'vuex'
import VueRouter from 'vue-router'
import HelloWorldComponent from './hello_world.vue'
import Board from './Board.vue'
import Eisenhower from './Eisenhower.vue'
import Moscow from './Moscow.vue'

import store from '../store'

import LiquorTree from '../liquor-tree/src/main.js'

import { autosizeDirective } from '../autosize.js'

import "../app.scss";
import "../scripts/shared.js";

Vue.use(LiquorTree)
Vue.use(Vuex)
Vue.use(VueRouter)
Vue.directive('autosize', autosizeDirective)

// Helper function to get CSRF token and make fetch requests
const apiRequest = async (url, options = {}) => {
    const token = document.body.querySelector('[name=csrfmiddlewaretoken]');
    const defaultHeaders = {
        'X-CSRFToken': token ? token.value : '',
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(url, {
        ...options,
        headers: defaultHeaders
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
};

const routes = [
    { path: '/', component: Board },
    { path: '/board/:slug', component: Board },
    { path: '/eisenhower', component: Eisenhower },
    { path: '/eisenhower/:slug', component: Eisenhower },
    { path: '/moscow', component: Moscow },
    { path: '/moscow/:slug', component: Moscow },
]

const router = new VueRouter({
    routes
})

new Vue({
    render: h => h(HelloWorldComponent),
    store: new Vuex.Store(store),

    router,

    created() {
       // CSRF token is now handled in the apiRequest helper function
    }
}).$mount('#app')
