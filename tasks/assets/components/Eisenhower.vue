<template>
    <div class="board eisenhower">
        <BoardTopbar />

        <div class="eisenhower-layout">
            <div class="task-tree-pane">
                <ul class="task-tree">
                    <li
                        v-for="item in flatItems"
                        :key="item.pathKey"
                        class="task-item"
                        :class="{
                            classified: item.eisenhower,
                            checked: item.checked
                        }"
                        :style="{ paddingLeft: (0.5 + item.depth * 1.2) + 'rem' }"
                        draggable="true"
                        @dragstart="onDragStart($event, item)"
                    >
                        <span
                            class="eisenhower-badge"
                            :class="item.eisenhower ? `badge-${item.eisenhower}` : 'badge-empty'"
                            :title="item.eisenhower ? quadrantTitleById[item.eisenhower] : ''"
                        ></span>
                        <span class="task-text">{{ item.text }}</span>
                    </li>
                </ul>
            </div>

            <div class="eisenhower-grid">
                <div
                    v-for="quadrant in quadrants"
                    :key="quadrant.id"
                    class="quadrant"
                    :class="`q-${quadrant.id}`"
                    @dragover.prevent="onDragOver"
                    @drop="onDrop($event, quadrant.id)"
                >
                    <h3>{{ quadrant.title }}</h3>
                    <ul>
                        <li
                            v-for="item in itemsByQuadrant[quadrant.id]"
                            :key="item.pathKey"
                            class="grid-item"
                            :class="{ checked: item.checked }"
                            draggable="true"
                            @dragstart="onDragStart($event, item)"
                            @contextmenu.prevent="showContextMenu($event, item)"
                        >
                            {{ item.text }}
                        </li>
                    </ul>
                </div>
            </div>
        </div>

        <div
            v-if="contextMenu.visible"
            class="context-menu"
            :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
            @click.stop
        >
            <button @click="removeStatus">Remove</button>
        </div>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useRoute } from 'vue-router'

import { storeToRefs } from 'pinia'

import { useBoardStore } from '../store'

import BoardTopbar from './BoardTopbar.vue'

const QUADRANTS = [
    { id: 'urgent-important', title: 'Urgent & Important – DO' },
    { id: 'not-urgent-important', title: 'Not Urgent & Important – SCHEDULE' },
    { id: 'urgent-not-important', title: 'Urgent & Not Important – DELEGATE' },
    { id: 'not-urgent-not-important', title: 'Not Urgent & Not Important – ELIMINATE' },
]

function deepClone(value) {
    return JSON.parse(JSON.stringify(value))
}

function getNodeByPath(state, path) {
    let cur = state[path[0]]
    for (let i = 1; i < path.length; i++) {
        cur = cur.children[path[i]]
    }
    return cur
}

const boardStore = useBoardStore()

const { currentBoard } = storeToRefs(boardStore)

const route = useRoute()

const contextMenu = ref({ visible: false, x: 0, y: 0, item: null })
const draggedItem = ref(null)

const quadrants = QUADRANTS

const quadrantTitleById = Object.fromEntries(QUADRANTS.map(q => [q.id, q.title]))

const flatItems = computed(() => {
    const items = []
    const traverse = (nodes, parentPath, depth) => {
        nodes.forEach((node, idx) => {
            const path = [...parentPath, idx]
            items.push({
                text: node.text,
                path,
                pathKey: path.join('/'),
                depth,
                eisenhower: node.data && node.data.meaningfulMarkers && node.data.meaningfulMarkers.eisenhower
                    ? node.data.meaningfulMarkers.eisenhower
                    : null,
                checked: node.state && node.state.checked,
            })
            if (node.children && node.children.length > 0) {
                traverse(node.children, path, depth + 1)
            }
        })
    }
    traverse(currentBoard.value.state || [], [], 0)
    return items
})

const itemsByQuadrant = computed(() => {
    const groups = Object.fromEntries(QUADRANTS.map(q => [q.id, []]))
    for (const item of flatItems.value) {
        if (item.eisenhower && groups[item.eisenhower]) {
            groups[item.eisenhower].push(item)
        }
    }
    return groups
})

onMounted(() => {
    if (route.params.slug) {
        boardStore.initBoard(route.params.slug)
    } else {
        const appElement = document.getElementById('app-meta')
        const defaultThread = appElement
            ? appElement.dataset.defaultThread
            : boardStore.currentThreadPtr.value
        boardStore.initBoard(defaultThread)
    }

    document.addEventListener('click', hideContextMenu)
})

onBeforeUnmount(() => {
    document.removeEventListener('click', hideContextMenu)
})

function onDragStart(ev, item) {
    draggedItem.value = item
    ev.dataTransfer.effectAllowed = 'move'
    ev.dataTransfer.setData('text/plain', item.pathKey)
}

function onDragOver(ev) {
    ev.dataTransfer.dropEffect = 'move'
}

function onDrop(ev, quadrantId) {
    if (!draggedItem.value) return
    setEisenhower(draggedItem.value.path, quadrantId)
    draggedItem.value = null
}

function setEisenhower(path, value) {
    const newState = deepClone(currentBoard.value.state)
    const node = getNodeByPath(newState, path)
    if (!node.data) node.data = {}
    if (!node.data.meaningfulMarkers) node.data.meaningfulMarkers = {}
    if (value === null) {
        delete node.data.meaningfulMarkers.eisenhower
    } else {
        node.data.meaningfulMarkers.eisenhower = value
    }
    boardStore.save({
        state: newState,
        focus: currentBoard.value.focus,
    })
}

function showContextMenu(ev, item) {
    contextMenu.value = {
        visible: true,
        x: ev.clientX,
        y: ev.clientY,
        item,
    }
}

function hideContextMenu() {
    contextMenu.value.visible = false
}

function removeStatus() {
    if (contextMenu.value.item) {
        setEisenhower(contextMenu.value.item.path, null)
    }
    hideContextMenu()
}
</script>

<style scoped>
.eisenhower-layout {
    display: flex;
    flex: 1;
    min-height: 0;
    height: calc(100vh - 8rem);
}

.task-tree-pane {
    width: 20%;
    min-width: 200px;
    overflow-y: auto;
    border-right: 1px solid #ddd;
    padding: 0.5rem 0;
}

.task-tree {
    list-style: none;
    padding: 0;
    margin: 0;
}

.task-item {
    padding: 0.3rem 0.5rem;
    cursor: grab;
    user-select: none;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    border-radius: 3px;
}

.task-item:active {
    cursor: grabbing;
}

.task-item:hover {
    background: #f0f0f0;
}

.task-item.classified {
    font-weight: 500;
    background: #f7f7fc;
}

.task-item.checked .task-text {
    text-decoration: line-through;
    color: #888;
}

.task-text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.eisenhower-badge {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 1px solid #ccc;
}

.badge-empty {
    background: transparent;
    border-color: #ddd;
}

.badge-urgent-important { background: #d9534f; border-color: #d9534f; }
.badge-not-urgent-important { background: #5cb85c; border-color: #5cb85c; }
.badge-urgent-not-important { background: #f0ad4e; border-color: #f0ad4e; }
.badge-not-urgent-not-important { background: #888; border-color: #888; }

.eisenhower-grid {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 0.5rem;
    padding: 0.5rem;
    min-height: 0;
}

.quadrant {
    border: 2px dashed #ccc;
    border-radius: 4px;
    padding: 0.5rem;
    overflow-y: auto;
    background: #fafafa;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.quadrant h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
}

.q-urgent-important { border-color: #d9534f; }
.q-not-urgent-important { border-color: #5cb85c; }
.q-urgent-not-important { border-color: #f0ad4e; }
.q-not-urgent-not-important { border-color: #888; }

.quadrant ul {
    list-style: none;
    padding: 0;
    margin: 0;
    overflow-y: auto;
    flex: 1;
}

.grid-item {
    padding: 0.3rem 0.5rem;
    margin: 0.25rem 0;
    background: white;
    border: 1px solid #ddd;
    border-radius: 3px;
    cursor: grab;
}

.grid-item:active {
    cursor: grabbing;
}

.grid-item.checked {
    text-decoration: line-through;
    color: #888;
}

.context-menu {
    position: fixed;
    background: white;
    border: 1px solid #ccc;
    border-radius: 4px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    min-width: 120px;
}

.context-menu button {
    display: block;
    background: none;
    border: none;
    padding: 0.5rem 1rem;
    cursor: pointer;
    width: 100%;
    text-align: left;
}

.context-menu button:hover {
    background: #f0f0f0;
}
</style>
