<template>
    <div class="tree-list-view">
        <pre class="tree-list-content" ref="content">{{ formattedList }}</pre>
        <button class="copy-btn" @click="copyToClipboard">Copy</button>
    </div>
</template>

<script>
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useBoardStore } from '../stores/boardStore'

export default {
    setup() {
        const boardStore = useBoardStore()
        const { currentBoard } = storeToRefs(boardStore)

        const formattedList = computed(() => {
            const renderNodes = (nodes, depth) => {
                if (!nodes || nodes.length === 0) return ''

                const indent = '  '.repeat(depth)
                let result = []

                for (const node of nodes) {
                    const text = node.text || ''
                    const isChecked = node.state?.checked

                    let line = `${indent}- ${text}`
                    if (isChecked) {
                        line = `${indent}- ~~${text}~~`
                    }

                    result.push(line)

                    if (node.children && node.children.length > 0) {
                        const childrenText = renderNodes(node.children, depth + 1)
                        if (childrenText) {
                            result.push(childrenText)
                        }
                    }
                }

                return result.join('\n')
            }

            return renderNodes(currentBoard.value.state, 0)
        })

        function copyToClipboard() {
            navigator.clipboard.writeText(formattedList.value)
        }

        return {
            currentBoard,
            formattedList,
            copyToClipboard
        }
    }
}
</script>

<style scoped>
.tree-list-view {
    padding: 1rem;
    position: relative;
}

.tree-list-content {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 1rem;
    margin: 0;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 14px;
    overflow-x: auto;
}

.copy-btn {
    position: absolute;
    top: 1.5rem;
    right: 1.5rem;
    padding: 0.25rem 0.5rem;
    font-size: 12px;
    background: #6c757d;
    color: white;
    border: none;
    border-radius: 3px;
    cursor: pointer;
}

.copy-btn:hover {
    background: #5a6268;
}
</style>
