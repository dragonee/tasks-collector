<template>
    <div class="board">
        <div class="upper-pane">
            <h1>Journal</h1>
        </div>

        <div class="middle-pane">
            <div class="calendar">
            </div>

            <div class="daily">
            </div>
        </div>

        <div class="lower-pane">
            <router-link to="/">Board</router-link>
            <router-link to="/journal">Journal</router-link>
        </div>
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

        normalContext() {
            return !this.editingContext
        },

        startDate() {
            return moment(this.currentBoard.date_started).format('YYYY-MM-DD')
        },
    },

    data: () => ({
        editingContext: false,
        focus: "",
    }),

    methods: {
        async addItem() {
            const node = this.$refs.tree.append(createTreeItem('Hi'))

            node.select()

            await promisifyTimeout(500)

            this.$refs.tree.find(node).startEditing()
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
