<template>
    <div class="board">
        <div class="upper-pane">
            <h1>Journal</h1>
        </div>

        <div class="middle-pane">
            <div class="calendar">
            </div>

            <div class="daily">
            </div>
        </div>

        <div class="lower-pane">
            <router-link to="/">Board</router-link>
            <router-link to="/journal">Journal</router-link>
        </div>
    </div>
</template>
<script>
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useBoardStore } from '../stores/boardStore'
import { createTreeItem, promisifyTimeout } from '../utils'

import NodeContent from './NodeContent.vue'

import moment from 'moment'

export default {
    components: {
        NodeContent
    },

    setup() {
        const boardStore = useBoardStore()
        const tree = ref(null)

        const { currentBoard, allThreads } = storeToRefs(boardStore)

        const editingContext = ref(false)
        const focus = ref("")

        const normalContext = computed(() => !editingContext.value)

        const startDate = computed(() => {
            return moment(currentBoard.value.date_started).format('YYYY-MM-DD')
        })

        async function addItem() {
            if (!tree.value) return

            const node = tree.value.append(createTreeItem('Hi'))
            node.select()

            await promisifyTimeout(500)

            tree.value.find(node).startEditing()
        }

        function saveState() {
            if (!tree.value) return

            boardStore.save({
                state: tree.value.toJSON(),
                focus: focus.value
            })
        }

        async function changeThread(ev) {
            await boardStore.changeThread(ev.target.value)
        }

        return {
            tree,
            currentBoard,
            allThreads,
            editingContext,
            focus,
            normalContext,
            startDate,
            addItem,
            saveState,
            changeThread,
            close: boardStore.close,
        }
    }
}
</script>
