<template>
    <div>
        <span
            v-if="markers.moscow"
            class="node-badge moscow"
            :class="`moscow-${markers.moscow}`"
            :title="moscowTitle"
        >{{ moscowLabel }}</span>

        <span
            v-if="markers.eisenhower"
            class="node-badge eisenhower"
            :class="`eisenhower-${markers.eisenhower}`"
            :title="eisenhowerTitle"
        >{{ eisenhowerLabel }}</span>

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

    </div>
</template>
<script>

export default {

    props: {
        node: Object,
    },

    computed: {
        markers() {
            return this.node.data.meaningfulMarkers
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

        eisenhowerLabel() {
            const labels = {
                'urgent-important': 'UI',
                'not-urgent-important': '.I',
                'urgent-not-important': 'U.',
                'not-urgent-not-important': '..',
            }
            return labels[this.markers.eisenhower] || ''
        },

        moscowTitle() {
            const titles = {
                'must': 'Must have',
                'should': 'Should have',
                'could': 'Could have',
                'wont': "Won't have",
            }
            return titles[this.markers.moscow] || ''
        },

        moscowLabel() {
            const labels = {
                'must': 'Mu',
                'should': 'Sh',
                'could': 'Co',
                'wont': 'Wh',
            }
            return labels[this.markers.moscow] || ''
        }
    },
}
</script>

