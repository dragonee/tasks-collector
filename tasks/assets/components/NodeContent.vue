<template>
    <div :class="rowClasses">
        {{ node.text }}

        <span v-if="markers.madeProgress">
            <span class="spacer"></span>
            <span
                class="dots full madeProgress"
                data-dots="1"
                title="1">
                    <span class="dot">
                    </span>
            </span>
        </span>

        <span v-else-if="markers.weeksInList > 0 && !markers.canBePostponed" class="weeksInListSpan">
            <span class="spacer"></span>

            <span
                v-if="cappedWeeksInList > 0"
                class="dots weeksInList"
                :data-dots="cappedWeeksInList"
                :title="markers.weeksInList">
                    <span class="dot" v-for="n in cappedWeeksInList">
                    </span>
            </span>
            <span
                v-if="violetDotsCount > 0"
                class="dots weeksInList violet"
                :data-dots="violetDotsCount"
                :title="`removal in ${6 - markers.weeksInList} commits`">
                    <span class="dot" v-for="n in violetDotsCount">
                    </span>
            </span>
        </span>

        <span v-if="markers.important > 0">
            <span class="spacer"></span>

            <span
                class="dots important"
                :data-dots="cappedImportant"
                :title="markers.important">
                    <span class="dot" v-for="n in cappedImportant">
                    </span>
            </span>
        </span>

        <span v-if="markers.finalizing" class="has-finalizing">
        </span>

        <span v-if="markers.canBePostponed" class="transition">
            ⟳
        </span>

        <span v-if="markers.transition" class="transition">
            ⇒ {{ markers.transition }}
        </span>

        <span
            v-if="markers.eisenhower"
            class="has-eisenhower"
            :class="`eisenhower-${markers.eisenhower}`"
            :title="eisenhowerTitle"
        >
        </span>

        <span
            v-if="markers.moscow"
            class="has-moscow"
            :class="`moscow-${markers.moscow}`"
            :title="moscowTitle"
        >
        </span>

    </div>
</template>
<script>

const FILTER_MODES = [
    'important',
    'deprecated',
    'finalizing',
    'moscow-must', 'moscow-should', 'moscow-could', 'moscow-wont',
    'eisenhower-urgent-important', 'eisenhower-not-urgent-important',
    'eisenhower-urgent-not-important', 'eisenhower-not-urgent-not-important',
]

function nodeMatchesMode(node, mode) {
    const markers = node.data?.meaningfulMarkers || {}

    if (mode === 'important') return (markers.important || 0) > 0

    if (mode === 'deprecated') {
        if ((markers.weeksInList || 0) < 5) return false
        if (node.hasChildren && node.hasChildren()) return false
        if (markers.canBePostponed) return false
        if ((markers.postponedFor || 0) > 0) return false
        if (markers.madeProgress) return false
        if (node.states?.checked) return false
        return true
    }

    if (mode === 'finalizing') return !!markers.finalizing
    if (mode.startsWith('moscow-')) return markers.moscow === mode.slice('moscow-'.length)
    if (mode.startsWith('eisenhower-')) return markers.eisenhower === mode.slice('eisenhower-'.length)

    return false
}

export default {

    props: {
        node: Object,
    },

    computed: {
        markers() {
            return this.node.data.meaningfulMarkers
        },

        descendantMatchModes() {
            const modes = new Set()
            const walk = (n) => {
                const children = n.children || []
                for (const child of children) {
                    for (const m of FILTER_MODES) {
                        if (nodeMatchesMode(child, m)) modes.add(m)
                    }
                    walk(child)
                }
            }
            walk(this.node)
            return modes
        },

        rowClasses() {
            const classes = {}

            for (const mode of this.descendantMatchModes) {
                classes[`has-children-${mode}`] = true
            }

            const active = this.$store.state.filterMode
            if (active !== 'all') {
                const selfMatches = nodeMatchesMode(this.node, active)
                classes['filter-hidden'] = !selfMatches && !this.descendantMatchModes.has(active)
            }

            return classes
        },

        cappedWeeksInList() {
            // Show blue dots only for weeks 1-3
            if (this.markers.weeksInList >= 4) return 0
            return this.markers.weeksInList
        },
        
        violetDotsCount() {
            if (this.markers.weeksInList === 4) return 2
            if (this.markers.weeksInList >= 5) return 1
            return 0
        },

        cappedImportant() {
            return Math.min(this.markers.important, 3)
        },

        eisenhowerTitle() {
            const titles = {
                'urgent-important': 'Urgent & Important',
                'not-urgent-important': 'Not Urgent & Important',
                'urgent-not-important': 'Urgent & Not Important',
                'not-urgent-not-important': 'Not Urgent & Not Important',
            }
            return titles[this.markers.eisenhower] || ''
        },

        moscowTitle() {
            const titles = {
                'must': 'Must have',
                'should': 'Should have',
                'could': 'Could have',
                'wont': "Won't have",
            }
            return titles[this.markers.moscow] || ''
        }
    },
}
</script>

