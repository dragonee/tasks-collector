<template>
    <div class="board">
        <div class="upper-pane">
            <h1>{{ startDate }}: <input v-model="focus" @blur="saveState" @keyup.stop></h1>
        </div>

        <tree
            v-show="!listViewMode"
            :data="currentBoard.state"
            :options="options"
            ref="tree"
        >
            <template slot-scope="{ node }">
                <node-content :node="node" class="tree-text">
                </node-content>
            </template>
        </tree>

        <TreeListView v-show="listViewMode" />

        <div class="lower-pane">
            <button @click.prevent="addItem">+</button>
            <select @change="changeThread($event)">
                <option v-for="thread in threads" :key="thread.id" :value="thread.id" :selected="thread.id == currentThreadId">
                    {{ thread.name }}
                </option>
            </select>

            <button @click.prevent="toggleListViewMode" class="secondary">{{ listViewMode ? 'tree' : 'list' }}</button>

            <router-link class="menulink" to="/">Board</router-link>
            <router-link class="menulink" to="/journal">Journal</router-link>
            <router-link class="menulink" to="/eisenhower">Eisenhower</router-link>
            <router-link class="menulink" to="/moscow">MoSCoW</router-link>

            <span class="menulink">/</span>

            <a class="menulink" href="/">Daily</a>
            <a class="menulink" href="/todo/">Tasks</a>
            <a class="menulink" href="/observations/">Observations</a>
            <a class="menulink" href="/admin/tree/observation/add/">+Observation</a>
            <a class="menulink" href="/summaries/">Summaries</a>
            <a class="menulink" href="/quests/">Quests</a>
            <a class="menulink" href="/quests/view/">Journal</a>
            <a class="menulink" href="/accounts/settings/">⚙</a>

            <select
                v-show="!listViewMode"
                v-model="filterMode"
                class="filter-select on-right"
            >
                <option value="all">all</option>
                <option value="important">important</option>
                <option value="deprecated">deprecated</option>
                <option value="finalizing">finalizing</option>
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

            <button @click.prevent="prepareCommit" :class="{ 'on-right': listViewMode }">commit</button>
        </div>

        <CommitConfirmationModal
            :show="showCommitModal"
            :items-to-remove="itemsToRemove"
            @confirm="confirmCommit"
            @cancel="cancelCommit"
        />

        <GlobalEvents
            v-if="normalContext"
            @keyup.i="addItem"
        />

        <GlobalEvents
            target="window"
            @focus="reloadBoards"
        />
    </div>
</template>
<script>

import { mapGetters, mapActions, mapState } from 'vuex'

import { createTreeItem, promisifyTimeout } from '../utils'

import GlobalEvents from 'vue-global-events'

import NodeContent from './NodeContent.vue'

import CommitConfirmationModal from './CommitConfirmationModal.vue'

import TreeListView from './TreeListView.vue'

import moment from 'moment'

export default {

    components: {
        GlobalEvents,
        NodeContent,
        CommitConfirmationModal,
        TreeListView
    },

    computed: {
        ...mapGetters([
            'currentBoard',
            'threads',
            'currentThreadId',
        ]),

        filterMode: {
            get() { return this.$store.state.filterMode },
            set(value) { this.$store.commit('setFilterMode', value) }
        },

        normalContext() {
            return !this.editingContext
        },

        startDate() {
            return moment(this.currentBoard.date_started).format('YYYY-MM-DD')
        },

        itemsToRemove() {
            return this.findItemsToBeRemoved(this.currentBoard.state)
        },

        options() {
            return {
                checkbox: true,
                editing: true,
                dnd: true,
                deletion: true,
                keyboardNavigation: true,

                store: {
                    store: this.$store,
                    getter: () => this.$store.getters.currentBoard.state,
                    dispatcher: (tree) => {
                        return this.$store.dispatch('save', {
                            state: tree,
                            focus: this.focus,
                        })
                    }
                }
            }
        }
    },

    data: () => ({
        editingContext: false,
        focus: "",
        unwatch: null,
        showCommitModal: false,
        listViewMode: false,
    }),

    watch: {
        filterMode(newMode) {
            if (newMode !== 'all' && this.$refs.tree) {
                this.$refs.tree.expandAll()
            }
        }
    },

    mounted() {
        this.$refs.tree.$on('node:text:changed', (node, text, old) => {
            // console.log('changed text', node, text, old)
        })

        this.$refs.tree.$on('node:editing:start', (node) => {
            this.editingContext = true
        })

        this.$refs.tree.$on('node:editing:stop', (node) => {
            this.editingContext = false

            //this.$store.dispatch('save', this.$refs.tree.toJSON())
        })

        this.unwatch = this.$store.watch(
            (state, getters) => getters.currentBoard,
            () => {
                this.focus = this.currentBoard.focus;
                
                const path = `/board/${this.currentBoard.thread.name}`;

                if (this.$route.path !== path) {
                    this.$router.push(path);
                }
            }
        )

        if (this.$route.params.slug) {
            this.$store.dispatch('initBoard', this.$route.params.slug);
        } else {
            const appElement = document.getElementById('app-meta');
       
            const defaultThread = appElement 
                ? appElement.dataset.defaultThread 
                : this.$store.state.currentThreadPtr.Name;
            
            this.$store.dispatch('initBoard', defaultThread);
        }

        if (this.$store.getters.currentBoard) {
            this.focus = this.$store.getters.currentBoard.focus
        }
    },

    beforeDestroy() {
        this.unwatch()
    },

    methods: {
        toggleListViewMode() {
            this.listViewMode = !this.listViewMode
        },

        async addItem() {
            const node = this.$refs.tree.append(createTreeItem('Hi'))

            /*
            await promisifyTimeout(500)

            node.vm.$el.querySelector('.tree-anchor')
                .dispatchEvent(new Event('dblclick'))

            //node.select()

            //this.$refs.tree.find(node).startEditing()
            */
        },

        ...mapActions([
            'close',
            'reloadBoards',
        ]),

        saveState() {
            this.$store.dispatch('save', {
                state: this.$refs.tree.toJSON(),
                focus: this.focus
            })
        },

        async changeThread(ev) {
            await this.$store.dispatch(
                'changeThread',
                ev.target.value
            )
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

<style scoped>
    .secondary {
        background-color: #c4c4c4;
        border: none;
        border-radius: 3px;
        cursor: pointer;
        margin: 0 0.5rem;

        &:hover {
            background-color: #bbbaba;
        }
    }
</style>