<template>
    <div class="board moscow">
        <div class="upper-pane">
            <h1>MoSCoW Classification</h1>
        </div>

        <div class="moscow-layout">
            <div class="task-tree-pane">
                <ul class="task-tree">
                    <li
                        v-for="item in flatItems"
                        :key="item.pathKey"
                        class="task-item"
                        :class="{
                            classified: item.moscow,
                            checked: item.checked
                        }"
                        :style="{ paddingLeft: (0.5 + item.depth * 1.2) + 'rem' }"
                        draggable="true"
                        @dragstart="onDragStart($event, item)"
                    >
                        <span
                            class="moscow-badge"
                            :class="item.moscow ? `badge-${item.moscow}` : 'badge-empty'"
                            :title="item.moscow ? bucketTitleById[item.moscow] : ''"
                        ></span>
                        <span class="task-text">{{ item.text }}</span>
                    </li>
                </ul>
            </div>

            <div class="moscow-grid">
                <div
                    v-for="bucket in buckets"
                    :key="bucket.id"
                    class="bucket"
                    :class="`b-${bucket.id}`"
                    @dragover.prevent="onDragOver"
                    @drop="onDrop($event, bucket.id)"
                >
                    <h3>{{ bucket.title }}</h3>
                    <ul>
                        <li
                            v-for="item in itemsByBucket[bucket.id]"
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

        <div class="lower-pane">
            <router-link class="menulink" to="/">Board</router-link>
            <router-link class="menulink" to="/eisenhower">Eisenhower</router-link>
            <router-link class="menulink" to="/moscow">MoSCoW</router-link>
        </div>
    </div>
</template>

<script>
import { mapGetters } from 'vuex'

const BUCKETS = [
    { id: 'must', title: 'Must have' },
    { id: 'should', title: 'Should have' },
    { id: 'could', title: 'Could have' },
    { id: 'wont', title: "Won't have" },
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

export default {
    data: () => ({
        contextMenu: { visible: false, x: 0, y: 0, item: null },
        draggedItem: null,
    }),

    computed: {
        ...mapGetters(['currentBoard']),

        buckets() {
            return BUCKETS
        },

        flatItems() {
            const items = []
            const traverse = (nodes, parentPath, depth) => {
                nodes.forEach((node, idx) => {
                    const path = [...parentPath, idx]
                    items.push({
                        text: node.text,
                        path,
                        pathKey: path.join('/'),
                        depth,
                        moscow: node.data && node.data.meaningfulMarkers && node.data.meaningfulMarkers.moscow
                            ? node.data.meaningfulMarkers.moscow
                            : null,
                        checked: node.state && node.state.checked,
                    })
                    if (node.children && node.children.length > 0) {
                        traverse(node.children, path, depth + 1)
                    }
                })
            }
            traverse(this.currentBoard.state || [], [], 0)
            return items
        },

        bucketTitleById() {
            return Object.fromEntries(BUCKETS.map(b => [b.id, b.title]))
        },

        itemsByBucket() {
            const groups = Object.fromEntries(BUCKETS.map(b => [b.id, []]))
            for (const item of this.flatItems) {
                if (item.moscow && groups[item.moscow]) {
                    groups[item.moscow].push(item)
                }
            }
            return groups
        },
    },

    mounted() {
        if (this.$route.params.slug) {
            this.$store.dispatch('initBoard', this.$route.params.slug)
        } else {
            const appElement = document.getElementById('app-meta')
            const defaultThread = appElement
                ? appElement.dataset.defaultThread
                : this.$store.state.currentThreadPtr.value
            this.$store.dispatch('initBoard', defaultThread)
        }

        document.addEventListener('click', this.hideContextMenu)
    },

    beforeDestroy() {
        document.removeEventListener('click', this.hideContextMenu)
    },

    methods: {
        onDragStart(ev, item) {
            this.draggedItem = item
            ev.dataTransfer.effectAllowed = 'move'
            ev.dataTransfer.setData('text/plain', item.pathKey)
        },

        onDragOver(ev) {
            ev.dataTransfer.dropEffect = 'move'
        },

        onDrop(ev, bucketId) {
            if (!this.draggedItem) return
            this.setMoscow(this.draggedItem.path, bucketId)
            this.draggedItem = null
        },

        setMoscow(path, value) {
            const newState = deepClone(this.currentBoard.state)
            const node = getNodeByPath(newState, path)
            if (!node.data) node.data = {}
            if (!node.data.meaningfulMarkers) node.data.meaningfulMarkers = {}
            if (value === null) {
                delete node.data.meaningfulMarkers.moscow
            } else {
                node.data.meaningfulMarkers.moscow = value
            }
            this.$store.dispatch('save', {
                state: newState,
                focus: this.currentBoard.focus,
            })
        },

        showContextMenu(ev, item) {
            this.contextMenu = {
                visible: true,
                x: ev.clientX,
                y: ev.clientY,
                item,
            }
        },

        hideContextMenu() {
            this.contextMenu.visible = false
        },

        removeStatus() {
            if (this.contextMenu.item) {
                this.setMoscow(this.contextMenu.item.path, null)
            }
            this.hideContextMenu()
        },
    },
}
</script>

<style scoped>
.moscow-layout {
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

.moscow-badge {
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

.badge-must { background: #b91c1c; border-color: #b91c1c; }
.badge-should { background: #d97706; border-color: #d97706; }
.badge-could { background: #0d9488; border-color: #0d9488; }
.badge-wont { background: #64748b; border-color: #64748b; }

.moscow-grid {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 0.5rem;
    padding: 0.5rem;
    min-height: 0;
}

.bucket {
    border: 2px dashed #ccc;
    border-radius: 4px;
    padding: 0.5rem;
    overflow-y: auto;
    background: #fafafa;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.bucket h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
}

.b-must { border-color: #b91c1c; }
.b-should { border-color: #d97706; }
.b-could { border-color: #0d9488; }
.b-wont { border-color: #64748b; }

.bucket ul {
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
