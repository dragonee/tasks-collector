<template>
    <div class="board">
        <BoardTopbar />

        <tree
            v-show="!listViewMode"
            :options="options"
            ref="tree"
        ></tree>

        <TreeListView v-show="listViewMode" />

        <GlobalEvents
            v-if="normalContext"
            @keyup.i="addItem"
        />

        <GlobalEvents
            target="window"
            @focus="reloadBoards"
        />
    </div>
</template>
<script>

import { mapGetters, mapActions } from 'vuex'

import { createTreeItem } from '../utils'

import GlobalEvents from 'vue-global-events'

import BoardTopbar from './BoardTopbar.vue'

import TreeListView from './TreeListView.vue'

export default {

    components: {
        GlobalEvents,
        BoardTopbar,
        TreeListView
    },

    computed: {
        ...mapGetters([
            'currentBoard',
        ]),

        listViewMode() {
            return this.$store.state.listViewMode
        },

        normalContext() {
            return !this.editingContext
        },

        options() {
            return {
                store: {
                    store: this.$store,
                    getter: () => this.$store.getters.currentBoard.state,
                    dispatcher: (tree) => {
                        return this.$store.dispatch('save', {
                            state: tree,
                            focus: this.$store.getters.currentBoard.focus,
                        })
                    }
                }
            }
        }
    },

    data: () => ({
        editingContext: false,
        unwatch: null,
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

            // an item added with `i` and left blank is a cancelled insert
            if (!node.text) {
                node.remove()
            }
        })

        this.unwatch = this.$store.watch(
            (state, getters) => getters.currentBoard,
            () => {
                const path = `/board/${this.currentBoard.thread.name}`;

                if (this.$route.path !== path) {
                    this.$router.push(path);
                }
            }
        )

        if (this.$route.params.slug) {
            this.$store.dispatch('initBoard', this.$route.params.slug);
        } else {
            const appElement = document.getElementById('app-meta');

            const defaultThread = appElement
                ? appElement.dataset.defaultThread
                : this.$store.state.currentThreadPtr.Name;

            this.$store.dispatch('initBoard', defaultThread);
        }
    },

    beforeDestroy() {
        this.unwatch()
    },

    methods: {
        async addItem() {
            const node = this.$refs.tree.append(createTreeItem())

            node.startEditing()
        },

        ...mapActions([
            'reloadBoards',
        ]),
    }
}
</script>
