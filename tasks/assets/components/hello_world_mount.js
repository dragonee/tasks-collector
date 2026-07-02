import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import HelloWorldComponent from './hello_world.vue'
import Board from './Board.vue'
import Eisenhower from './Eisenhower.vue'
import Moscow from './Moscow.vue'

import TreeRoot from '../liquor-tree/src/components/TreeRoot.vue'

import { autosizeDirective } from '../autosize.js'

import "../app.scss";
import "../scripts/shared.js";

const routes = [
    { path: '/', component: Board },
    { path: '/board/:slug', component: Board },
    { path: '/eisenhower', component: Eisenhower },
    { path: '/eisenhower/:slug', component: Eisenhower },
    { path: '/moscow', component: Moscow },
    { path: '/moscow/:slug', component: Moscow },
]

const router = createRouter({
    history: createWebHashHistory(),
    routes,
})

const app = createApp(HelloWorldComponent)

app.component(TreeRoot.name, TreeRoot)
app.use(createPinia())
app.use(router)
app.directive('autosize', autosizeDirective)

app.mount('#app')
