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

import { createTreeItem, createBoard } from './utils'

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


export default {
    state: {
        listResponse: null,
        threads: null,
        currentThreadPtr: name_ptr(DEFAULT_NAME),
    },

    getters: {
        currentBoard(state) {
            return state.listResponse && state.listResponse.count
                ? state.listResponse.results[0]
                : createBoard()
        },

        // empty?
        currentThread(state) {
            return state.threads && state.threads.count
                ? state.threads.results.find(state.currentThreadPtr.finder)
                : null;
        },

        currentThreadId(state, getters) {
            return getters.currentThread?.id;
        },

        threads(state) {
            return  state.threads && state.threads.count
                ? state.threads.results
                : [];
        }
    },

    mutations: {
        setListResponse(state, payload) {
            state.listResponse = payload
        },

        updateBoardInListResponse(state, payload) {
            const index = state.listResponse.results.findIndex((item) => {
                item.id === payload.id
            })

            if (index === -1) {
                state.listResponse.results.splice(0, 0, payload)
            } else {
                state.listResponse.results.splice(index, 1, payload)
            }

            state.listResponse.count = state.listResponse.results.length
        },

        setThreads(state, threads) {
            state.threads = threads;
        },

        setCurrentThreadId(state, threadId) {
            state.currentThreadPtr = id_ptr(threadId);
        },

        setCurrentThreadName(state, threadName) {
            state.currentThreadPtr = name_ptr(threadName);
        }
    },

    actions: {
        async initThreads({ commit, dispatch, getters }) {
            const threadResponse = await apiRequest('/threads/')

            commit('setThreads', threadResponse);
        },
        
        async initBoard({ commit, dispatch, getters }, threadName) {
            await dispatch('initThreads')

            commit('setCurrentThreadName', threadName);

            await dispatch('loadBoardsForThread', getters.currentThread.id)
        },

        async loadBoardsForThread({ commit, getters }, threadId) {
            if (!threadId) {
                return;
            }

            const listResponse = await apiRequest(`/boards/?thread=${threadId}`)

            commit('setListResponse', listResponse)
        },

        async reloadBoards({ dispatch, getters }) {
            await dispatch('loadBoardsForThread', getters.currentThreadId);
        },

        async changeThread({ dispatch, commit }, threadId) {
            commit('setCurrentThreadId', threadId)

            await dispatch('loadBoardsForThread', threadId)
        },

        async save({ commit, getters }, payload) {
            const newBoard = {
                ...getters.currentBoard,
                ...payload
            }

            if (equal(payload.state, getters.currentBoard.state) && payload.focus === getters.currentBoard.focus) {
                return;
            }

            commit('updateBoardInListResponse', newBoard)

            const board = await apiRequest(`/boards/${newBoard.id}/`, {
                method: 'PUT',
                body: JSON.stringify(newBoard)
            })

            commit('updateBoardInListResponse', board)
        },

        async close({ commit, getters }, payload) {
            const oldBoard = getters.currentBoard

            const board = await apiRequest(`/boards/${oldBoard.id}/commit/`, {
                method: 'POST'
            })

            commit('updateBoardInListResponse', board)
        }
    }
}