<template>
  <div role="tree" :class="{'tree': true, 'tree--draggable' : !!draggableNode}">
    <ul class="tree-root" @dragstart="onDragStart">
      <TreeNode
        v-for="node in visibleNodes"

        :key="node.id"
        :node="node"
        :options="opts"
      />
    </ul>

    <ContextMenu ref="menu">
        <template #default="child">
           <li class="v-context__sub">
                <a>Importance</a>
                <ul class="v-context v-context-inline">
                    <li>
                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 1 })">1</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 2 })">2</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 3 })">3</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 0 })">Reset</a>
                    </li>
                </ul>
            </li>

            <li>
                <a href="#" @click.prevent="onClick('finalizing', { ...child.data  })">Clearable</a>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('madeProgress', { ...child.data  })">Made progress</a>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('canBePostponed', { ...child.data  })">⟳ Repeat</a>
            </li>

            <li class="v-context__sub">
                 <a>Postpone for</a>
                 <ul class="v-context v-context-inline">
                     <li>
                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 1 })">1</a>

                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 2 })">2</a>

                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 3 })">3</a>
                     </li>
                 </ul>
             </li>

             <li class="v-context__sub" v-if="currentThread">
                <a>Move to</a>

                <ul class="v-context">
                    <li>
                        <a href="#" v-if="currentThread.name != 'Sidetrack'" @click.prevent="onClick('transition', {... child.data, value: 'Sidetrack' })">Sidetrack</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name != 'Daily'" @click.prevent="onClick('transition', {... child.data, value: 'Daily' })">Daily</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name == 'Books'" @click.prevent="onClick('transition', {... child.data, value: 'Read' })">Read (backlog)</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name != 'Trash'" @click.prevent="onClick('transition', {... child.data, value: 'Trash' })">🗑 Trash</a>
                    </li>
                    <li>
                        <a href="#" @click.prevent="onClick('transition', {... child.data, value: UNSET })">Clear</a>
                    </li>
                </ul>
            </li>
            <li class="v-context__sub">
                <a>Add to Plan</a>

                <ul class="v-context">
                    <li>
                        <a href="#" @click.prevent="onClick('addToPlan', {... child.data, value: 'today' })">Today</a>
                    </li>
                    <li>
                        <a href="#" @click.prevent="onClick('addToPlan', {... child.data, value: 'tomorrow' })">Tomorrow</a>
                    </li>
                    <li>
                        <a href="#" @click.prevent="onClick('addToPlan', {... child.data, value: 'this_week' })">This Week</a>
                    </li>
                </ul>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('remove', { ...child.data  })">Remove</a>
            </li>

       </template>
   </ContextMenu>

    <DraggableNode v-if="draggableNode" :target="draggableNode" />
  </div>
</template>

<script>
  import { computed } from 'vue'

  import TreeNode from './TreeNode'
  import DraggableNode from './DraggableNode'
  import ContextMenu from './ContextMenu'
  import TreeMixin from '../mixins/TreeMixin'
  import TreeDnd from '../mixins/DndMixin'
  import Tree from '../lib/Tree'

  import { Notifier } from '../../../notifier';
  import { MEANINGFUL_MARKER_KEYS } from '../../../utils.js';

  const UNSET = '__UNSET';

  const defaults = {
    nodeIndent: 24
  }

  const changeMeaningfulMarker = (data, object) => ({
      ...data,
      meaningfulMarkers: {
          ...data.meaningfulMarkers,
          ...object,
      }
  });

  const clearMeaningfulMarker = (data, key) => {
      let markers = {...data.meaningfulMarkers}

      delete markers[key]

      return {
          ...data,
          meaningfulMarkers: markers,
      };
  };

  export default {
    name: 'Tree',
    components: {
      TreeNode,
      DraggableNode,
      ContextMenu
    },

    mixins: [TreeMixin, TreeDnd],

    provide() {
        return {
            // the Tree instance only exists after mounted; a computed ref
            // late-binds it for the injecting TreeNodes
            tree: computed(() => this.tree),
            menu: () => this.$refs.menu,
        }
    },

    props: {
      options: {
        type: Object,
        default: _ => ({})
      }
    },

    methods: {
        async onClick(method, { node, value }) {
            const markerMethods = [...MEANINGFUL_MARKER_KEYS, 'transition'];

            if (markerMethods.includes(method)) {
                if (value === undefined) {
                    value = !node.data.meaningfulMarkers[method]
                }

                if (value === UNSET) {
                    node.data = clearMeaningfulMarker(node.data, method)
                } else {
                    node.data = changeMeaningfulMarker(node.data, {
                        [method]: value
                    })
                }

                if (method === 'postponedFor') {
                    node.hide()
                }

                this.tree.$emit('LIQUOR_NOISE')
            } else if (method === 'addToPlan') {
                const taskText = node.data.text
                const timeframe = value  // 'today', 'tomorrow', 'this_week'
                const notifier = Notifier({ time: 3000 })

                try {
                    const response = await fetch('/plans/add-task/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken(),
                        },
                        body: JSON.stringify({
                            text: taskText,
                            timeframe: timeframe
                        })
                    })

                    if (!response.ok) {
                        const errorData = await response.json()
                        notifier.error(errorData.error || 'Failed to add task to plan')
                        return
                    }

                    const timeframeLabel = timeframe === 'this_week' ? 'this week' : timeframe
                    notifier.success(`Task added to ${timeframeLabel}'s plan`)
                } catch (error) {
                    notifier.error(`Error: ${error.message}`)
                }
            } else if (method === 'remove') {
                node.remove()
            }
        },
        getCsrfToken() {
            const token = document.body.querySelector('[name=csrfmiddlewaretoken]')
            return token ? token.value : ''
        }
    },

    computed: {
        currentThread() {
            return this.opts.store?.store?.currentThread ?? null
        },

        visibleNodes() {
            return (this.model || []).filter(node => node && node.visible())
        },
    },

    data () {
      // we should not mutating a prop directly...
      // that's why we have to create a new object
      // TODO: add method for changing options
      let opts = Object.assign({}, defaults, this.options)

      return {
        model: null,
        tree: null,
        opts,
        draggableNode: null,
        UNSET,
      }
    }
  }
</script>

