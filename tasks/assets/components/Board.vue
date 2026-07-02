<template>
    <div class="board">
        <BoardTopbar />

        <tree
            v-show="!listViewMode"
            :options="options"
            ref="tree"
            @node:editing:start="onNodeEditingStart"
            @node:editing:stop="onNodeEditingStop"
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

import { mapStores, mapState, mapActions } from 'pinia'

import { useBoardStore } from '../store'

import { createTreeItem } from '../utils'

import { GlobalEvents } from 'vue-global-events'

import BoardTopbar from './BoardTopbar.vue'

import TreeListView from './TreeListView.vue'

export default {

    components: {
        GlobalEvents,
        BoardTopbar,
        TreeListView
    },

    computed: {
        ...mapStores(useBoardStore),

        ...mapState(useBoardStore, [
            'currentBoard',
            'listViewMode',
        ]),

        normalContext() {
            return !this.editingContext
        },

        options() {
            const store = this.boardStore

            return {
                store: {
                    store,
                    getter: () => store.currentBoard.state,
                    dispatcher: (tree) => {
                        return store.save({
                            state: tree,
                            focus: store.currentBoard.focus,
                        })
                    }
                }
            }
        }
    },

    data: () => ({
        editingContext: false,
    }),

    watch: {
        currentBoard() {
            const path = `/board/${this.currentBoard.thread.name}`;

            if (this.$route.path !== path) {
                this.$router.push(path);
            }
        }
    },

    mounted() {
        if (this.$route.params.slug) {
            this.boardStore.initBoard(this.$route.params.slug);
        } else {
            const appElement = document.getElementById('app-meta');

            const defaultThread = appElement
                ? appElement.dataset.defaultThread
                : this.boardStore.currentThreadPtr.value;

            this.boardStore.initBoard(defaultThread);
        }
    },

    methods: {
        async addItem() {
            const node = this.$refs.tree.append(createTreeItem())

            node.startEditing()
        },

        onNodeEditingStart(node) {
            this.editingContext = true
        },

        onNodeEditingStop(node) {
            this.editingContext = false

            // an item added with `i` and left blank is a cancelled insert
            if (!node.text) {
                node.remove()
            }
        },

        ...mapActions(useBoardStore, [
            'reloadBoards',
        ]),
    }
}
</script>
