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
                canBeDoneOutsideOfWork: false,
                canBePostponed: false,
                // 0+
                postponedFor: 0,
                hiddenWhenPostponed: false,
            },

            state: "open",
        },

        text: text,

        children: [],
    }
}

export function createBoard() {
    return {
        date_closed: null,
        date_started: null,
        id: null,
        state: []
    }
}