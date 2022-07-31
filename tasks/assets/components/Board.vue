<template>
    <div class="board">
        <div class="upper-pane">
            <h1>{{ startDate }}: <input v-model="focus" @blur="saveState" @keyup.stop></h1>
        </div>

        <tree
            :data="currentBoard.state"
            :options="options"
            ref="tree"


        >
            <template slot-scope="{ node }">
                <node-content :node="node" class="tree-text">
                </node-content>
            </template>
        </tree>

        <div class="lower-pane">
            <button @click.prevent="addItem">+</button>
            <select @change="changeThread($event)">
                <option v-for="thread in threads" :key="thread.id" :value="thread.id" :selected="thread.id == currentThreadId">
                    {{ thread.name }}
                </option>
            </select>

            <router-link class="menulink" to="/">Board</router-link>
            <router-link class="menulink" to="/journal">Journal</router-link>

            <span class="menulink">/</span>

            <a class="menulink" href="/">Daily</a>
            <a class="menulink" href="/hello/world/">Tasks</a>
            <a class="menulink" href="/observations/">Observations</a>
            <a class="menulink" href="/admin/tree/observation/add/">+Observation</a>
            <a class="menulink" href="/periodical/">Periodical</a>
            <a class="menulink" href="/summaries/">Summaries</a>
            <a class="menulink" href="/quests/view/">Quests</a>

            <button @click.prevent="close" class="on-right">commit</button>
        </div>

        <GlobalEvents
            v-if="normalContext"
            @keyup.i="addItem"
        />
    </div>
</template>
<script>

import { mapGetters, mapActions, mapState } from 'vuex'

import { createTreeItem, promisifyTimeout } from '../utils'

import GlobalEvents from 'vue-global-events'

import NodeContent from './NodeContent.vue'

import moment from 'moment'

export default {

    components: {
        GlobalEvents,
        NodeContent
    },

    computed: {
        ...mapGetters([
            'currentBoard',
            'threads',
        ]),

        ...mapState([
            'currentThreadId'
        ]),

        normalContext() {
            return !this.editingContext
        },

        startDate() {
            return moment(this.currentBoard.date_started).format('YYYY-MM-DD')
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
    }),

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
            (state, getters) => getters.currentBoard.focus,
            () => {
                this.focus = this.currentBoard.focus
            }
        )

        if (this.$store.getters.currentBoard) {
            this.focus = this.$store.getters.currentBoard.focus
        }
    },

    beforeDestroy() {
        this.unwatch()
    },

    methods: {
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
        }

    }
}
</script>
