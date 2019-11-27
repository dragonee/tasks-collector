<template>
    <div class="board">
        <div class="upper-pane">
            <h1>{{ startDate }}</h1>
        </div>

        <tree
            :data="currentBoard.state"
            :options="options"
            ref="tree"


        >
            <template slot-scope="{ node }">
                <node-content :node="node" class="tree-text">
                </node-content>
            </template>
        </tree>

        <div class="lower-pane">
            <button @click.prevent="addItem">+</button>
            <button @click.prevent="close" class="on-right">commit</button>
        </div>

        <GlobalEvents
            v-if="normalContext"
            @keyup.i="addItem"
        />
    </div>
</template>
<script>

import { mapGetters, mapActions } from 'vuex'

import { createTreeItem, promisifyTimeout } from '../utils'

import GlobalEvents from 'vue-global-events'

import NodeContent from './NodeContent.vue'

import moment from 'moment'

export default {

    components: {
        GlobalEvents,
        NodeContent
    },

    computed: {
        ...mapGetters([
            'currentBoard'
        ]),

        normalContext() {
            return !this.editingContext
        },

        startDate() {
            return moment(this.currentBoard.date_started).format('YYYY-MM-DD')
        },

        options() {
            return {
                checkbox: true,
                editing: true,
                dnd: true,
                deletion: true,
                keyboardNavigation: true,

                store: {
                    store: this.$store,
                    getter: () => this.$store.getters.currentBoard.state,
                    dispatcher: (tree) => {
                        return this.$store.dispatch('save', tree)
                    }
                }
            }
        }
    },

    data: () => ({
        editingContext: false,
    }),

    mounted() {
        this.$refs.tree.$on('node:text:changed', (node, text, old) => {
            // console.log('changed text', node, text, old)
        })

        this.$refs.tree.$on('node:editing:start', (node) => {
            this.editingContext = true
        })

        this.$refs.tree.$on('node:editing:stop', (node) => {
            this.editingContext = false

            //this.$store.dispatch('save', this.$refs.tree.toJSON())
        })
    },

    methods: {
        async addItem() {
            const node = this.$refs.tree.append(createTreeItem('Hi'))

            node.select()

            await promisifyTimeout(500)

            this.$refs.tree.find(node).startEditing()
        },

        ...mapActions([
            'close'
        ]),

    }
}
</script>
