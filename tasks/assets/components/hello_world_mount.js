import Vue from 'vue'
import Vuex from 'vuex'
import HelloWorldComponent from './hello_world.vue'

import store from '../store'

import LiquorTree from 'liquor-tree'

Vue.use(LiquorTree)
Vue.use(Vuex)

import axios from 'axios'


new Vue({
    render: h => h(HelloWorldComponent),
    store: new Vuex.Store(store),

    mounted() {
       this.$store.dispatch('init')
    },

    created() {
       let token = document.body.querySelector('[name=csrfmiddlewaretoken]');
       axios.defaults.headers.common['X-CSRFToken'] = token.value;
    }
}).$mount('#app')
