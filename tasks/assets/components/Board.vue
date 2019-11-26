<template>
    <div class="board">
        <tree
            :data="currentBoard.state"
            :options="options"
            ref="tree"


        >
            <div
                class="tree-text"
                slot-scope="{ node }"
            >
                {{ node.text }}
                {{ node.data.meaningfulMarkers.weeksInList }}
            </div>
        </tree>

        <button @click.prevent="addItem">+</button>

        <GlobalEvents
            v-if="normalContext"
            @keyup.i="addItem"
        />
    </div>
</template>
<script>

import { mapGetters } from 'vuex'

import { createTreeItem, promisifyTimeout } from '../utils'

import GlobalEvents from 'vue-global-events'


export default {

    components: {
        GlobalEvents,
    },

    computed: {
        ...mapGetters([
            'currentBoard'
        ]),

        normalContext() {
            return !this.editingContext
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



    }
}
</script>
