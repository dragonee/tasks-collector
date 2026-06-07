<template>
    <div class="topbar">
        <div class="upper-pane">
            <h1>{{ startDate }}: <input v-model="focus" @blur="onFocusBlur" @keyup.stop></h1>
            <button @click.prevent="prepareCommit" class="on-right">Commit</button>
        </div>

        <div class="lower-pane board-controls">
            <label class="control">
                <span class="control-label">Thread</span>
                <select :value="currentThreadId" @change="onThreadChange($event)">
                    <option v-for="thread in threads" :key="thread.id" :value="thread.id">
                        {{ thread.name }}
                    </option>
                </select>
            </label>

            <label class="control">
                <span class="control-label">Mode</span>
                <select :value="currentMode" @change="onModeChange($event)">
                    <option value="board">Board</option>
                    <option value="eisenhower">Eisenhower</option>
                    <option value="moscow">MoSCoW</option>
                </select>
            </label>

            <label v-if="currentMode === 'board' && !listViewMode" class="control">
                <span class="control-label">Filter</span>
                <select v-model="filterMode" class="filter-select">
                    <option value="all">all</option>
                    <option value="important">important</option>
                    <option value="deprecated">deprecated</option>
                    <option value="finalizing">clearable</option>
                    <optgroup label="MoSCoW">
                        <option value="moscow-must">Must have</option>
                        <option value="moscow-should">Should have</option>
                        <option value="moscow-could">Could have</option>
                        <option value="moscow-wont">Won't have</option>
                    </optgroup>
                    <optgroup label="Eisenhower">
                        <option value="eisenhower-urgent-important">Urgent &amp; Important</option>
                        <option value="eisenhower-not-urgent-important">Not Urgent &amp; Important</option>
                        <option value="eisenhower-urgent-not-important">Urgent &amp; Not Important</option>
                        <option value="eisenhower-not-urgent-not-important">Not Urgent &amp; Not Important</option>
                    </optgroup>
                </select>
            </label>

            <label v-if="currentMode === 'board'" class="control">
                <span class="control-label">Display</span>
                <select v-model="displayMode">
                    <option value="list">list</option>
                    <option value="tree">tree</option>
                </select>
            </label>
        </div>

        <CommitConfirmationModal
            :show="showCommitModal"
            :items-to-remove="itemsToRemove"
            @confirm="confirmCommit"
            @cancel="cancelCommit"
        />
    </div>
</template>

<script>

import { mapGetters, mapActions } from 'vuex'

import moment from 'moment'

import CommitConfirmationModal from './CommitConfirmationModal.vue'

export default {

    components: {
        CommitConfirmationModal,
    },

    data: () => ({
        focus: "",
        showCommitModal: false,
        unwatch: null,
    }),

    computed: {
        ...mapGetters([
            'currentBoard',
            'threads',
            'currentThread',
            'currentThreadId',
        ]),

        currentMode() {
            const path = this.$route.path
            if (path.startsWith('/eisenhower')) return 'eisenhower'
            if (path.startsWith('/moscow')) return 'moscow'
            return 'board'
        },

        filterMode: {
            get() { return this.$store.state.filterMode },
            set(value) { this.$store.commit('setFilterMode', value) }
        },

        displayMode: {
            get() { return this.$store.state.listViewMode ? 'list' : 'tree' },
            set(value) { this.$store.commit('setListViewMode', value === 'list') }
        },

        startDate() {
            return moment(this.currentBoard.date_started).format('YYYY-MM-DD')
        },

        itemsToRemove() {
            return this.findItemsToBeRemoved(this.currentBoard.state)
        },
    },

    mounted() {
        this.focus = this.currentBoard.focus

        this.unwatch = this.$store.watch(
            (state, getters) => getters.currentBoard,
            () => {
                this.focus = this.currentBoard.focus
            }
        )
    },

    beforeDestroy() {
        this.unwatch()
    },

    methods: {
        ...mapActions([
            'close',
        ]),

        onFocusBlur() {
            this.$store.dispatch('saveFocus', this.focus)
        },

        onThreadChange(ev) {
            this.$store.dispatch('changeThread', Number(ev.target.value))
        },

        onModeChange(ev) {
            const mode = ev.target.value
            const name = this.currentThread?.name

            const base = mode === 'board' ? '/board' : `/${mode}`
            const path = name
                ? `${base}/${name}`
                : (mode === 'board' ? '/' : base)

            if (this.$route.path !== path) {
                this.$router.push(path)
            }
        },

        isItemDeprecated(item) {
            const markers = item.data?.meaningfulMarkers || {}

            if ((markers.weeksInList || 0) < 5) {
                return false
            }

            if (item.children && item.children.length > 0) {
                return false
            }

            if (markers.canBePostponed) {
                return false
            }

            if ((markers.postponedFor || 0) > 0) {
                return false
            }

            if (markers.madeProgress) {
                return false
            }

            if (item.state?.checked) {
                return false
            }

            return true
        },

        findItemsToBeRemoved(items) {
            let result = []

            const traverse = (node) => {
                if (this.isItemDeprecated(node)) {
                    result.push({
                        text: node.text,
                        weeksInList: node.data?.meaningfulMarkers?.weeksInList || 0
                    })
                }

                if (node.children && node.children.length > 0) {
                    node.children.forEach(child => traverse(child))
                }
            }

            items.forEach(item => traverse(item))
            return result
        },

        prepareCommit() {
            this.showCommitModal = true
        },

        confirmCommit() {
            this.showCommitModal = false
            this.close()
        },

        cancelCommit() {
            this.showCommitModal = false
        }
    }
}
</script>
