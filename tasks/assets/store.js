import axios from 'axios'

import { createTreeItem, createBoard } from './utils'

import equal from 'deep-equal'

export default {
    state: {
        listResponse: null,
    },

    getters: {
        currentBoard(state) {
            return state.listResponse && state.listResponse.count
                ? state.listResponse.results[0]
                : createBoard()
        },
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
        }
    },

    actions: {
        async init({ commit }) {
            const listResponse = await axios.get('/boards/')

            commit('setListResponse', listResponse.data)
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