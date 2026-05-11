export function treeItemForRootAndPath(root, path) {
    return path.reduce((cur, pathChunk) => {
        if (cur === undefined) {
            return undefined
        }

        return cur[pathChunk]
    }, root)
}

export function createTreeItem(text="") {
    return {
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