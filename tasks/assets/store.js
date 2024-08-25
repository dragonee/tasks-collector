import axios from 'axios'

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
        async init({ commit, dispatch, getters }) {
            const threadResponse = await axios.get('/threads/')

            commit('setThreads', threadResponse.data);

            await dispatch('loadBoardsForThread', getters.currentThread.id)
        },

        async loadBoardsForThread({ commit, getters }, threadId) {
            const listResponse = await axios.get(`/boards/?thread=${threadId}`)

            commit('setListResponse', listResponse.data)
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

            const board = await axios.put(`/boards/${newBoard.id}/`, newBoard)

            commit('updateBoardInListResponse', board.data)
        },

        async close({ commit, getters }, payload) {
            const oldBoard = getters.currentBoard

            const board = await axios.post(`/boards/${oldBoard.id}/commit/`)

            commit('updateBoardInListResponse', board.data)
        }
    }
}