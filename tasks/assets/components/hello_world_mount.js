import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'

import HelloWorldComponent from './hello_world.vue'
import Board from './Board.vue'
import Journal from './Journal.vue'

import LiquorTree from '../liquor-tree/src/main.js'

import "../app.scss"
import "../scripts/shared.js"
import '@imengyu/vue3-context-menu/lib/vue3-context-menu.css'

const routes = [
    { path: '/', component: Board },
    { path: '/board/:slug', component: Board },
    { path: '/journal/:date', component: Journal },
]

const router = createRouter({
    history: createWebHashHistory(),
    routes
})

const pinia = createPinia()

const app = createApp(HelloWorldComponent)

app.use(pinia)
app.use(router)
app.use(LiquorTree)

app.mount('#app')
