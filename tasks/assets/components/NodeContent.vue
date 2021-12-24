<template>
    <div>
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
        <span v-else-if="markers.weeksInList > 0" class="weeksInListSpan">
            <span class="spacer"></span>

            <span
                class="dots weeksInList"
                :data-dots="cappedWeeksInList"
                :title="markers.weeksInList">
                    <span class="dot" v-for="n in cappedWeeksInList">
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
            return Math.min(this.markers.weeksInList, 4)
        },

        cappedImportant() {
            return Math.min(this.markers.important, 3)
        }
    },
}
</script>
