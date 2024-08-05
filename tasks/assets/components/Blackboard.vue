<template>
    <div class="board whiteboard">
        <div class="blackboard">
            <div v-for="task in tasksPlaced" class="item" draggable="true" 
                :style="{left: task.data.placement.x + 'px', top: task.data.placement.y + 'px'}">
                {{ task.text }}
            </div>
        </div>

        <div class="upper-pane">
            <h1>Blackboard</h1>
        </div>


        <div class="shelf">
            <div v-for="task in tasksNotPlaced" class="item" draggable="true" @dragend="placeItem(task, $event)">
                {{ task.text }}
            </div>
        </div>

        <div class="lower-pane">
            <select @change="changeThread($event)">
                <option v-for="thread in threads" :key="thread.id" :value="thread.id" :selected="thread.id == currentThreadId">
                    {{ thread.name }}
                </option>
            </select>

            <router-link class="menulink" to="/">List</router-link>
            <router-link class="menulink" to="/board">Board</router-link>

            <span class="menulink">/</span>

            <a class="menulink" href="/">Daily</a>
            <a class="menulink" href="/todo/">Tasks</a>
            <a class="menulink" href="/observations/">Observations</a>
            <a class="menulink" href="/admin/tree/observation/add/">+Observation</a>
            <a class="menulink" href="/periodical/">Periodical</a>
            <a class="menulink" href="/summaries/">Summaries</a>
            <a class="menulink" href="/quests/">Quests</a>
            <a class="menulink" href="/quests/view/">Journal</a>

            <button @click.prevent="close" class="on-right">commit</button>
        </div>
    </div>
</template>
<script>

import { mapGetters, mapActions, mapState } from 'vuex'

import { createTreeItem, promisifyTimeout } from '../utils'

import GlobalEvents from 'vue-global-events'

import NodeContent from './NodeContent.vue'

import moment from 'moment'

// https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/drop_event

export default {

    components: {
        GlobalEvents,
        NodeContent
    },

    computed: {
        ...mapGetters([
            'currentBoard',
            'currentBoardFlat',
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

        tasksPlaced() {
            return this.currentBoardFlat.state.filter(
                (x) => x.data.placement
            )
        },

        tasksNotPlaced() {
            return this.currentBoardFlat.state.filter(
                (x) => !x.data.placement
            )
        }
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
        },

        placeItem(task, ev) {
            console.log(task, ev);

            const placement = {
                x: ev.clientX,
                y: ev.clientY,
            };

            task.data = {
                ...task.data,
                placement
            };
        },

    }
}
</script>
