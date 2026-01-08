<template>
  <component :is="tag" role="tree" :class="{'tree': true, 'tree-loading': loading, 'tree--draggable' : !!draggableNode}">
    <template v-if="filter && matches.length == 0" >
      <div class="tree-filter-empty" v-html="opts.filter.emptyText"></div>
    </template>
    <template v-else>
      <ul class="tree-root" @dragstart="onDragStart">
        <template v-if="opts.filter.plainList && matches.length > 0">
          <TreeNode
            v-for="node in visibleMatches"
            :key="node.id"
            :node="node"
            :options="opts"
          />
        </template>
        <template v-else>
          <TreeNode
            v-for="node in visibleModel"
            :key="node.id"
            :node="node"
            :options="opts"
          />
        </template>
      </ul>
    </template>

    <DraggableNode v-if="draggableNode" :target="draggableNode" />
  </component>
</template>

<script>
  import { computed, provide, ref } from 'vue'
  import ContextMenu from '@imengyu/vue3-context-menu'
  import TreeNode from './TreeNode'
  import DraggableNode from './DraggableNode'
  import TreeMixin from '../mixins/TreeMixin'
  import TreeDnd from '../mixins/DndMixin'

  import { useBoardStore } from '../../../stores/boardStore'
  import { Notifier } from '../../../notifier'

  const UNSET = '__UNSET'

  const defaults = {
    direction: 'ltr',
    multiple: true,
    checkbox: false,
    checkOnSelect: false,
    autoCheckChildren: true,
    autoDisableChildren: true,
    checkDisabledChildren: true,
    parentSelect: false,
    keyboardNavigation: true,
    nodeIndent: 24,
    minFetchDelay: 0,
    fetchData: null,
    propertyNames: null,
    deletion: false,
    dnd: false,
    editing: false,
    onFetchError: function(err) { throw err }
  }

  const changeMeaningfulMarker = (data, object) => ({
      ...data,
      meaningfulMarkers: {
          ...data.meaningfulMarkers,
          ...object,
      }
  })

  const clearMeaningfulMarker = (data, key) => {
      let markers = {...data.meaningfulMarkers}

      delete markers[key]

      return {
          ...data,
          meaningfulMarkers: markers,
      }
  }

  const filterDefaults = {
    emptyText: 'Nothing found!',
    matcher(query, node) {
      const isMatched = new RegExp(query, 'i').test(node.text)

      if (isMatched) {
        if (node.parent && new RegExp(query, 'i').test(node.parent.text)) {
          return false
        }
      }

      return isMatched
    },
    plainList: false,
    showChildren: true
  }

  export default {
    name: 'Tree',
    components: {
      TreeNode,
      DraggableNode,
    },

    mixins: [TreeMixin, TreeDnd],

    setup() {
      const boardStore = useBoardStore()
      const menuRef = ref(null)

      provide('tree', null)
      provide('menu', () => menuRef.value)

      return {
        boardStore,
        menuRef,
        currentThread: computed(() => boardStore.currentThread),
      }
    },

    props: {
      data: {},

      options: {
        type: Object,
        default: _ => ({})
      },

      filter: String,

      tag: {
        type: String,
        default: 'div'
      }
    },

    watch: {
      filter (term) {
        this.tree.filter(term)
      }
    },

    computed: {
      visibleMatches() {
        return this.matches.filter(node => node.visible())
      },
      visibleModel() {
        return (this.model || []).filter(node => node && node.visible())
      }
    },

    methods: {
        showContextMenu(event, node) {
            const threadName = this.currentThread?.name

            const importanceSubmenu = [
                { label: '1', onClick: () => this.onClick('important', { node, value: 1 }) },
                { label: '2', onClick: () => this.onClick('important', { node, value: 2 }) },
                { label: '3', onClick: () => this.onClick('important', { node, value: 3 }) },
                { label: 'Reset', onClick: () => this.onClick('important', { node, value: 0 }) },
            ]

            const postponeSubmenu = [
                { label: '1', onClick: () => this.onClick('postponedFor', { node, value: 1 }) },
                { label: '2', onClick: () => this.onClick('postponedFor', { node, value: 2 }) },
                { label: '3', onClick: () => this.onClick('postponedFor', { node, value: 3 }) },
            ]

            const moveToSubmenu = []
            if (threadName !== 'Sidetrack') {
                moveToSubmenu.push({ label: 'Sidetrack', onClick: () => this.onClick('transition', { node, value: 'Sidetrack' }) })
            }
            if (threadName !== 'Daily') {
                moveToSubmenu.push({ label: 'Daily', onClick: () => this.onClick('transition', { node, value: 'Daily' }) })
            }
            if (threadName === 'Books') {
                moveToSubmenu.push({ label: 'Read (backlog)', onClick: () => this.onClick('transition', { node, value: 'Read' }) })
            }
            if (threadName !== 'Trash') {
                moveToSubmenu.push({ label: 'Trash', onClick: () => this.onClick('transition', { node, value: 'Trash' }) })
            }
            moveToSubmenu.push({ label: 'Clear', onClick: () => this.onClick('transition', { node, value: UNSET }) })

            const addToPlanSubmenu = [
                { label: 'Today', onClick: () => this.onClick('addToPlan', { node, value: 'today' }) },
                { label: 'Tomorrow', onClick: () => this.onClick('addToPlan', { node, value: 'tomorrow' }) },
                { label: 'This Week', onClick: () => this.onClick('addToPlan', { node, value: 'this_week' }) },
            ]

            ContextMenu.showContextMenu({
                x: event.x,
                y: event.y,
                items: [
                    { label: 'Importance', children: importanceSubmenu },
                    { label: 'Clearable', onClick: () => this.onClick('finalizing', { node }) },
                    { label: 'Made progress', onClick: () => this.onClick('madeProgress', { node }) },
                    { label: 'Repeat', onClick: () => this.onClick('canBePostponed', { node }) },
                    { label: 'Postpone for', children: postponeSubmenu },
                    { label: 'Move to', children: moveToSubmenu },
                    { label: 'Add to Plan', children: addToPlanSubmenu },
                    { label: 'Remove', onClick: () => this.onClick('remove', { node }) },
                ]
            })
        },

        async onClick(method, { node, value }) {
            const markerMethods = [
                'weeksInList',
                'important',
                'finalizing',
                'canBeDoneOutsideOfWork',
                'canBePostponed',
                'postponedFor',
                'madeProgress',
                'transition',
            ]

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

                this.tree.emitter.emit('LIQUOR_NOISE')
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

    data () {
      // we should not mutating a prop directly...
      // that's why we have to create a new object
      // TODO: add method for changing options
      let opts = Object.assign({}, defaults, this.options)

      opts.filter = Object.assign(
        {},
        filterDefaults,
        opts.filter
      )

      return {
        model: null,
        tree: null,
        loading: false,
        opts,
        matches: [],
        draggableNode: null,
        UNSET,
      }
    }
  }
</script>
