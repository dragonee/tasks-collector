export function treeItemForRootAndPath(root, path) {
    return path.reduce((cur, pathChunk) => {
        if (cur === undefined) {
            return undefined
        }

        return cur[pathChunk]
    }, root)
}

function s4() {
    return Math.floor((1 + Math.random()) * 0x10000).toString(16).substring(1)
}

export function makeId() {
    return s4() + s4() + '-' + s4() + '-' + s4() + '-' + s4() + '-' + s4() + s4() + s4()
}

export function ensureItemIds(items) {
    if (!Array.isArray(items)) return
    for (const item of items) {
        if (!item.id) item.id = makeId()
        if (item.children) ensureItemIds(item.children)
    }
}

// The day it is here, as YYYY-MM-DD. The server's day (UTC) differs from it
// for part of every night.
export function localDate() {
    const now = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function eachItem(items, visit) {
    for (const item of items || []) {
        visit(item)
        eachItem(item.children, visit)
    }
}

// What was done to the items that have tasks, between the board as the server
// last gave it (`before`) and the tree about to be saved (`after`).
//
// A planned item is ticked when its task is done and reads as its task does,
// so ticking, unticking or rewording it is something done to the task. The
// server is told so in as many words: a tree alone doesn't say whether it is
// newer than what was done on the phone meanwhile.
export function taskOps(before, after) {
    const planned = new Map()
    eachItem(before, (item) => {
        if (item.data?.taskId) planned.set(item.id, item)
    })

    const ops = []
    eachItem(after, (item) => {
        const was = planned.get(item.id)
        if (!was) return

        const wasChecked = Boolean(was.state?.checked)
        const isChecked = Boolean(item.state?.checked)
        if (isChecked && !wasChecked) {
            ops.push({
                op: 'complete',
                item_id: item.id,
                day: localDate(),
                at: new Date().toISOString(),
                key: makeId(),
            })
        } else if (!isChecked && wasChecked) {
            ops.push({ op: 'reopen', item_id: item.id })
        }

        if (item.text && item.text !== was.text) {
            ops.push({ op: 'rename', item_id: item.id, text: item.text })
        }
    })
    return ops
}

export function createTreeItem(text="") {
    return {
        id: makeId(),
        data: {
            meaningfulMarkers: {
                weeksInList: 0,
                // 0...3
                important: 0,
                finalizing: false,
                eisenhower: null,
                moscow: null,
                canBeDoneOutsideOfWork: false,
                canBePostponed: false,
                // 0+
                postponedFor: 0,
                madeProgress: false,
            },

            state: "open",

            // The task made for this item once it is planned; none yet.
            taskId: null,
        },

        text: text,

        children: [],
    }
}

export function createBoard() {
    return {
        date_started: null,
        id: null,
        focus: "",
        state: []
    }
}

// Marker keys settable from the board tree UI (context menu / node classes).
export const MEANINGFUL_MARKER_KEYS = [
    'weeksInList',
    'important',
    'finalizing',
    'canBeDoneOutsideOfWork',
    'canBePostponed',
    'postponedFor',
    'madeProgress',
]

export const FILTER_MODES = [
    'important',
    'deprecated',
    'finalizing',
    'moscow-must', 'moscow-should', 'moscow-could', 'moscow-wont',
    'eisenhower-urgent-important', 'eisenhower-not-urgent-important',
    'eisenhower-urgent-not-important', 'eisenhower-not-urgent-not-important',
]

export function nodeMatchesMode(node, mode) {
    const markers = node.data?.meaningfulMarkers || {}

    if (mode === 'important') return (markers.important || 0) > 0

    if (mode === 'deprecated') {
        if ((markers.weeksInList || 0) < 5) return false
        if (node.children && node.children.length > 0) return false
        if (markers.canBePostponed) return false
        if ((markers.postponedFor || 0) > 0) return false
        if (markers.madeProgress) return false
        if (node.state?.checked) return false
        return true
    }

    if (mode === 'finalizing') return !!markers.finalizing
    if (mode.startsWith('moscow-')) return markers.moscow === mode.slice('moscow-'.length)
    if (mode.startsWith('eisenhower-')) return markers.eisenhower === mode.slice('eisenhower-'.length)

    return false
}

export function promisifyTimeout(ms) {
    return new Promise((resolve) => {
        setTimeout(() => resolve(), ms)
    })
}