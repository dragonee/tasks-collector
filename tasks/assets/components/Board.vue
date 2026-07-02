<template>
    <div class="board">
        <BoardTopbar />

        <Tree
            v-show="!listViewMode"
            :options="options"
            ref="tree"
            @node:editing:start="onNodeEditingStart"
            @node:editing:stop="onNodeEditingStop"
        ></Tree>

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
<script setup>

import { computed, onMounted, ref, watch } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { storeToRefs } from 'pinia'

import { useBoardStore } from '../store'

import { createTreeItem } from '../utils'

import { GlobalEvents } from 'vue-global-events'

import Tree from '../liquor-tree/src/components/TreeRoot.vue'

import BoardTopbar from './BoardTopbar.vue'

import TreeListView from './TreeListView.vue'

const boardStore = useBoardStore()

const { currentBoard, listViewMode } = storeToRefs(boardStore)

const route = useRoute()
const router = useRouter()

const tree = ref(null)

const editingContext = ref(false)

const normalContext = computed(() => !editingContext.value)

const options = {
    store: {
        store: boardStore,
        getter: () => boardStore.currentBoard.state,
        dispatcher: (state) => {
            return boardStore.save({
                state,
                focus: boardStore.currentBoard.focus,
            })
        }
    }
}

const reloadBoards = () => boardStore.reloadBoards()

watch(currentBoard, () => {
    const path = `/board/${currentBoard.value.thread.name}`;

    if (route.path !== path) {
        router.push(path);
    }
})

onMounted(() => {
    if (route.params.slug) {
        boardStore.initBoard(route.params.slug);
    } else {
        const appElement = document.getElementById('app-meta');

        const defaultThread = appElement
            ? appElement.dataset.defaultThread
            : boardStore.currentThreadPtr.value;

        boardStore.initBoard(defaultThread);
    }
})

async function addItem() {
    const node = tree.value.append(createTreeItem())

    node.startEditing()
}

function onNodeEditingStart(node) {
    editingContext.value = true
}

function onNodeEditingStop(node) {
    editingContext.value = false

    // an item added with `i` and left blank is a cancelled insert
    if (!node.text) {
        node.remove()
    }
}
</script>
