<template>
    <div class="board">
        <tree
            :data="currentBoard.state"
            :options="options"
            ref="tree"
        />

        <button @click.prevent="addItem">+</button>

    </div>
</template>
<script>
import { mapGetters } from 'vuex'

import { createTreeItem } from '../utils'

export default {

    computed: {
        ...mapGetters([
            'currentBoard'
        ]),

        options() {
            return {
                checkbox: true,
                editing: true,
                dnd: true,

                store: {
                    store: this.$store,
                    getter: () => this.$store.getters.currentBoard.state,
                    dispatcher: (tree) => {
                        this.$store.dispatch('save', tree)
                    }
                }
            }
        }
    },

    mounted() {
        this.$refs.tree.$on('node:text:changed', (node, text, old) => {
            // console.log('changed text', node, text, old)
        })
    },

    methods: {
        addItem() {
            this.$refs.tree.append(createTreeItem('Hi'))
        }

    }
}
</script>
