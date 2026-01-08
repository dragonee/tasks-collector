import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import equal from 'deep-equal'
import { createBoard } from '../utils'

const DEFAULT_NAME = 'Daily'

const ThreadPtrTypes = {
    Name: 'Name',
    Id: 'Id',
}

const name_ptr = (name) => ({
    type: ThreadPtrTypes.Name,
    value: name,
    finder: (x) => x.name === name,
})

const id_ptr = (id) => ({
    type: ThreadPtrTypes.Id,
    value: id,
    finder: (x) => x.id === id,
})

// Helper function to get CSRF token and make fetch requests
const apiRequest = async (url, options = {}) => {
    const token = document.body.querySelector('[name=csrfmiddlewaretoken]')
    const defaultHeaders = {
        'X-CSRFToken': token ? token.value : '',
        'Content-Type': 'application/json',
        ...options.headers
    }

    const response = await fetch(url, {
        ...options,
        headers: defaultHeaders
    })

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
}

export const useBoardStore = defineStore('board', () => {
    // State
    const listResponse = ref(null)
    const threads = ref(null)
    const currentThreadPtr = ref(name_ptr(DEFAULT_NAME))

    // Getters
    const currentBoard = computed(() => {
        return listResponse.value && listResponse.value.count
            ? listResponse.value.results[0]
            : createBoard()
    })

    const currentThread = computed(() => {
        return threads.value && threads.value.count
            ? threads.value.results.find(currentThreadPtr.value.finder)
            : null
    })

    const currentThreadId = computed(() => {
        return currentThread.value?.id
    })

    const allThreads = computed(() => {
        return threads.value && threads.value.count
            ? threads.value.results
            : []
    })

    // Actions
    function updateBoardInListResponse(payload) {
        const index = listResponse.value.results.findIndex((item) => {
            return item.id === payload.id
        })

        if (index === -1) {
            listResponse.value.results.splice(0, 0, payload)
        } else {
            listResponse.value.results.splice(index, 1, payload)
        }

        listResponse.value.count = listResponse.value.results.length
    }

    async function initThreads() {
        const threadResponse = await apiRequest('/threads/')
        threads.value = threadResponse
    }

    async function initBoard(threadName) {
        await initThreads()
        currentThreadPtr.value = name_ptr(threadName)
        await loadBoardsForThread(currentThread.value.id)
    }

    async function loadBoardsForThread(threadId) {
        if (!threadId) {
            return
        }

        const response = await apiRequest(`/boards/?thread=${threadId}`)
        listResponse.value = response
    }

    async function reloadBoards() {
        await loadBoardsForThread(currentThreadId.value)
    }

    async function changeThread(threadId) {
        currentThreadPtr.value = id_ptr(threadId)
        await loadBoardsForThread(threadId)
    }

    async function save(payload) {
        const newBoard = {
            ...currentBoard.value,
            ...payload
        }

        if (equal(payload.state, currentBoard.value.state) && payload.focus === currentBoard.value.focus) {
            return
        }

        updateBoardInListResponse(newBoard)

        const board = await apiRequest(`/boards/${newBoard.id}/`, {
            method: 'PUT',
            body: JSON.stringify(newBoard)
        })

        updateBoardInListResponse(board)
    }

    async function close() {
        const oldBoard = currentBoard.value

        const board = await apiRequest(`/boards/${oldBoard.id}/commit/`, {
            method: 'POST'
        })

        updateBoardInListResponse(board)
    }

    return {
        // State
        listResponse,
        threads,
        currentThreadPtr,

        // Getters
        currentBoard,
        currentThread,
        currentThreadId,
        allThreads,

        // Actions
        initThreads,
        initBoard,
        loadBoardsForThread,
        reloadBoards,
        changeThread,
        save,
        close,
    }
})
