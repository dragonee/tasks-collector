<template>
    <div class="board">
        <div class="upper-pane">
            <h1>{{ startDate }}: <input v-model="focus" @blur="saveState" @keyup.stop></h1>
        </div>

        <tree
            v-show="!listViewMode"
            :data="currentBoard.state"
            :options="options"
            ref="tree"
        >
            <template #default="{ node }">
                <node-content :node="node" class="tree-text">
                </node-content>
            </template>
        </tree>

        <TreeListView v-show="listViewMode" />

        <div class="lower-pane">
            <button @click.prevent="addItem">+</button>
            <select @change="changeThread($event)">
                <option v-for="thread in allThreads" :key="thread.id" :value="thread.id" :selected="thread.id == currentThreadId">
                    {{ thread.name }}
                </option>
            </select>

            <button @click.prevent="toggleListViewMode" class="secondary">{{ listViewMode ? 'tree' : 'list' }}</button>

            <router-link class="menulink" to="/">Board</router-link>
            <router-link class="menulink" to="/journal">Journal</router-link>

            <span class="menulink">/</span>

            <a class="menulink" href="/">Daily</a>
            <a class="menulink" href="/todo/">Tasks</a>
            <a class="menulink" href="/observations/">Observations</a>
            <a class="menulink" href="/admin/tree/observation/add/">+Observation</a>
            <a class="menulink" href="/summaries/">Summaries</a>
            <a class="menulink" href="/quests/">Quests</a>
            <a class="menulink" href="/quests/view/">Journal</a>
            <a class="menulink" href="/accounts/settings/">Settings</a>

            <button @click.prevent="prepareCommit" class="on-right">commit</button>
        </div>

        <CommitConfirmationModal
            :show="showCommitModal"
            :items-to-remove="itemsToRemove"
            @confirm="confirmCommit"
            @cancel="cancelCommit"
        />
    </div>
</template>
<script>
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'

import { useBoardStore } from '../stores/boardStore'
import { createTreeItem, promisifyTimeout } from '../utils'

import NodeContent from './NodeContent.vue'
import CommitConfirmationModal from './CommitConfirmationModal.vue'
import TreeListView from './TreeListView.vue'

import moment from 'moment'

export default {
    components: {
        NodeContent,
        CommitConfirmationModal,
        TreeListView
    },

    setup() {
        const boardStore = useBoardStore()
        const router = useRouter()
        const route = useRoute()
        const tree = ref(null)

        const { currentBoard, allThreads, currentThreadId } = storeToRefs(boardStore)

        const editingContext = ref(false)
        const focus = ref("")
        const showCommitModal = ref(false)
        const listViewMode = ref(false)

        // Window focus event listener
        const handleWindowFocus = () => {
            boardStore.reloadBoards()
        }

        // Keyboard event listener
        const handleKeyup = (e) => {
            if (e.key === 'i' && !editingContext.value) {
                addItem()
            }
        }

        const normalContext = computed(() => !editingContext.value)

        const startDate = computed(() => {
            return moment(currentBoard.value.date_started).format('YYYY-MM-DD')
        })

        const itemsToRemove = computed(() => {
            return findItemsToBeRemoved(currentBoard.value.state)
        })

        const options = computed(() => ({
            checkbox: true,
            editing: true,
            dnd: true,
            deletion: true,
            keyboardNavigation: true,

            store: {
                store: boardStore,
                getter: () => boardStore.currentBoard.state,
                dispatcher: (treeData) => {
                    return boardStore.save({
                        state: treeData,
                        focus: focus.value,
                    })
                }
            }
        }))

        function toggleListViewMode() {
            listViewMode.value = !listViewMode.value
        }

        function addItem() {
            if (tree.value) {
                tree.value.append(createTreeItem('Hi'))
            }
        }

        function saveState() {
            if (tree.value) {
                boardStore.save({
                    state: tree.value.toJSON(),
                    focus: focus.value
                })
            }
        }

        async function changeThread(ev) {
            await boardStore.changeThread(ev.target.value)
        }

        function findItemsToBeRemoved(items) {
            let result = []

            const willBeForceRemoved = (node) => {
                const markers = node.data?.meaningfulMarkers || {}

                // Only show items with weeksInList >= 5 that will be force-removed
                const weeksInList = markers.weeksInList || 0
                if (weeksInList < 5) {
                    return false
                }

                // Keep categories (nodes with children)
                if (node.children && node.children.length > 0) {
                    return false
                }

                // Keep canBePostponed tasks
                if (markers.canBePostponed) {
                    return false
                }

                // Keep postponed tasks
                if ((markers.postponedFor || 0) > 0) {
                    return false
                }

                // Keep tasks that made progress
                if (markers.madeProgress) {
                    return false
                }

                // Do not show checked tasks
                if (node.state?.checked) {
                    return false
                }

                return true
            }

            const traverse = (node) => {
                if (willBeForceRemoved(node)) {
                    result.push({
                        text: node.text,
                        weeksInList: node.data?.meaningfulMarkers?.weeksInList || 0
                    })
                }

                if (node.children && node.children.length > 0) {
                    node.children.forEach(child => traverse(child))
                }
            }

            if (items) {
                items.forEach(item => traverse(item))
            }
            return result
        }

        function prepareCommit() {
            showCommitModal.value = true
        }

        function confirmCommit() {
            showCommitModal.value = false
            boardStore.close()
        }

        function cancelCommit() {
            showCommitModal.value = false
        }

        onMounted(() => {
            // Set up tree event listeners
            if (tree.value && tree.value.tree) {
                tree.value.tree.$on('node:text:changed', (args) => {
                    // console.log('changed text', args)
                })

                tree.value.tree.$on('node:editing:start', () => {
                    editingContext.value = true
                })

                tree.value.tree.$on('node:editing:stop', () => {
                    editingContext.value = false
                })
            }

            // Set up window focus listener
            window.addEventListener('focus', handleWindowFocus)
            document.addEventListener('keyup', handleKeyup)

            // Initialize board
            if (route.params.slug) {
                boardStore.initBoard(route.params.slug)
            } else {
                const appElement = document.getElementById('app-meta')
                const defaultThread = appElement
                    ? appElement.dataset.defaultThread
                    : 'Daily'
                boardStore.initBoard(defaultThread)
            }

            if (boardStore.currentBoard) {
                focus.value = boardStore.currentBoard.focus
            }
        })

        // Watch for currentBoard changes
        watch(currentBoard, (newBoard) => {
            if (newBoard) {
                focus.value = newBoard.focus || ""

                if (newBoard.thread) {
                    const path = `/board/${newBoard.thread.name}`
                    if (route.path !== path) {
                        router.push(path)
                    }
                }
            }
        })

        onBeforeUnmount(() => {
            window.removeEventListener('focus', handleWindowFocus)
            document.removeEventListener('keyup', handleKeyup)
        })

        return {
            tree,
            currentBoard,
            allThreads,
            currentThreadId,
            editingContext,
            focus,
            showCommitModal,
            listViewMode,
            normalContext,
            startDate,
            itemsToRemove,
            options,
            toggleListViewMode,
            addItem,
            saveState,
            changeThread,
            prepareCommit,
            confirmCommit,
            cancelCommit,
            close: boardStore.close,
            reloadBoards: boardStore.reloadBoards,
        }
    }
}
</script>

<style scoped>
    .secondary {
        background-color: #c4c4c4;
        border: none;
        border-radius: 3px;
        cursor: pointer;
        margin: 0 0.5rem;

        &:hover {
            background-color: #bbbaba;
        }
    }
</style>
