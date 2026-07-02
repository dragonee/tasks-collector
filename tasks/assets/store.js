import { defineStore } from 'pinia'

// Helper function to get CSRF token and make fetch requests
const apiRequest = async (url, options = {}) => {
    const token = document.body.querySelector('[name=csrfmiddlewaretoken]');
    const defaultHeaders = {
        'X-CSRFToken': token ? token.value : '',
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(url, {
        ...options,
        headers: defaultHeaders
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
};

import { createTreeItem, createBoard, FILTER_MODES, nodeMatchesMode, ensureItemIds } from './utils'

import equal from 'deep-equal'

const DEFAULT_NAME = 'Daily'

const ThreadPtrTypes = {
    Name: 'Name',
    Id: 'Id',
};

const name_ptr = (name) => ({
    type: ThreadPtrTypes.Name,
    value: name,
    finder: (x) => {
        return x.name === name
    },
});

const id_ptr = (id) => ({
    type: ThreadPtrTypes.Id,
    value: id,
    finder: (x) => {
        return x.id === id
    },
});


export const useBoardStore = defineStore('board', {
    state: () => ({
        listResponse: null,
        // named threadsResponse (not threads) so the `threads` getter can keep
        // the name the components use
        threadsResponse: null,
        currentThreadPtr: name_ptr(DEFAULT_NAME),
        filterMode: 'all',
        listViewMode: false,
    }),

    getters: {
        currentBoard(state) {
            return state.listResponse && state.listResponse.count
                ? state.listResponse.results[0]
                : createBoard()
        },

        // empty?
        currentThread(state) {
            return state.threadsResponse && state.threadsResponse.count
                ? state.threadsResponse.results.find(state.currentThreadPtr.finder)
                : null;
        },

        currentThreadId() {
            return this.currentThread?.id;
        },

        threads(state) {
            return state.threadsResponse && state.threadsResponse.count
                ? state.threadsResponse.results
                : [];
        },

        nodeFilterMatches() {
            const result = new Map()
            const walk = (node) => {
                const self = new Set()
                for (const mode of FILTER_MODES) {
                    if (nodeMatchesMode(node, mode)) self.add(mode)
                }

                const descendants = new Set()
                for (const child of (node.children || [])) {
                    walk(child)
                    const entry = result.get(child.id)
                    if (entry) {
                        for (const m of entry.self) descendants.add(m)
                        for (const m of entry.descendants) descendants.add(m)
                    }
                }

                result.set(node.id, { self, descendants })
            }
            for (const root of (this.currentBoard.state || [])) {
                walk(root)
            }
            return result
        }
    },

    actions: {
        setListResponse(payload) {
            for (const board of payload?.results || []) {
                ensureItemIds(board.state)
            }
            this.listResponse = payload
        },

        updateBoardInListResponse(payload) {
            ensureItemIds(payload.state)

            const index = this.listResponse.results.findIndex(
                (item) => item.id === payload.id
            )

            if (index === -1) {
                this.listResponse.results.splice(0, 0, payload)
            } else {
                this.listResponse.results.splice(index, 1, payload)
            }

            this.listResponse.count = this.listResponse.results.length
        },

        setCurrentThreadId(threadId) {
            this.currentThreadPtr = id_ptr(threadId);
        },

        setCurrentThreadName(threadName) {
            this.currentThreadPtr = name_ptr(threadName);
        },

        setFilterMode(mode) {
            this.filterMode = mode;
        },

        setListViewMode(listViewMode) {
            this.listViewMode = listViewMode;
        },

        async initThreads() {
            const threadResponse = await apiRequest('/threads/')

            this.threadsResponse = threadResponse;
        },

        async initBoard(threadName) {
            await this.initThreads()

            this.setCurrentThreadName(threadName);

            await this.loadBoardsForThread(this.currentThread.id)
        },

        async loadBoardsForThread(threadId) {
            if (!threadId) {
                return;
            }

            const listResponse = await apiRequest(`/boards/?thread=${threadId}`)

            this.setListResponse(listResponse)
        },

        async reloadBoards() {
            await this.loadBoardsForThread(this.currentThreadId);
        },

        async changeThread(threadId) {
            this.setCurrentThreadId(threadId)

            await this.loadBoardsForThread(threadId)
        },

        async saveFocus(focus) {
            await this.save({
                state: this.currentBoard.state,
                focus,
            })
        },

        async save(payload) {
            const newBoard = {
                ...this.currentBoard,
                ...payload
            }

            if (equal(payload.state, this.currentBoard.state) && payload.focus === this.currentBoard.focus) {
                return;
            }

            this.updateBoardInListResponse(newBoard)

            const board = await apiRequest(`/boards/${newBoard.id}/`, {
                method: 'PUT',
                body: JSON.stringify(newBoard)
            })

            this.updateBoardInListResponse(board)
        },

        async close() {
            const oldBoard = this.currentBoard

            const board = await apiRequest(`/boards/${oldBoard.id}/commit/`, {
                method: 'POST'
            })

            this.updateBoardInListResponse(board)
        }
    }
})
