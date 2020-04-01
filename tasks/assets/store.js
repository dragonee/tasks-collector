import axios from 'axios'

import { createTreeItem, createBoard } from './utils'

import equal from 'deep-equal'

const DEFAULT_NAME = 'Daily'

export default {
    state: {
        listResponse: null,
        threads: null,
        currentThreadId: 0,
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
                ? state.threads.results.find(x => x.id == state.currentThreadId)
                : null;
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

        setThreads(state, {threads, current}) {
            state.threads = threads
            // default thread
            state.currentThreadId = current || threads.results.find(
                item => item.name == DEFAULT_NAME
            ).id || threads.results[0].id
        },

        setCurrentThreadId(state, threadId) {
            state.currentThreadId = threadId
        }
    },

    actions: {
        async init({ commit, dispatch, getters }) {
            const threadResponse = await axios.get('/threads/')

            commit('setThreads', {
                threads: threadResponse.data
            })

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