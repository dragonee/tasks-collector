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