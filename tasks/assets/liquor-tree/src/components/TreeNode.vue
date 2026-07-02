<template>
  <li class="tree-node" :data-id="node.id" :class="nodeClass" @mousedown.stop="handleMouseDown" @contextmenu.stop.prevent="openMenu">
    <div class="tree-content" :style="{'padding-left': padding}" @click="select">
      <i
        class="tree-arrow"
        :class="{'expanded': node.states.expanded, 'has-child': node.children.length}"
        @click.stop="toggleExpand">
      </i>

      <i
        class="tree-checkbox"
        :class="{'checked': node.states.checked, 'indeterminate': node.states.indeterminate}"
        @click.stop="check">
      </i>

      <span
        class="tree-anchor"
        tabindex="-1"
        ref="anchor"
        @focus="onNodeFocus"
        @dblclick="tree.$emit('node:dblclick', node)">
          <node-content :node="node" />
      </span>
    </div>

    <transition name="l-fade">
      <ul
        v-if="hasChildren() && node.states.expanded"
        class="tree-children">
          <node
            v-for="child in node.children"
            v-if="child && child.visible()"

            :key="child.id"
            :node="child"
            :options="options"
            >
          </node>
      </ul>
    </transition>
  </li>
</template>

<script>
  import NodeContent from './NodeContent'

  const TreeNode = {
    name: 'Node',
    inject: ['tree', 'menu'],
    props: ['node', 'options'],

    components: {
      NodeContent
    },

    watch: {
      node() {
        this.node.vm = this
      }
    },

    data() {
      this.node.vm = this

      return {}
    },

    computed: {
      padding() {
        return this.node.depth * this.options.nodeIndent + 'px'
      },

      nodeClass() {
        let state = this.node.states
        let hasChildren = this.hasChildren()
        let classes = {
          'has-child': hasChildren,
          'expanded': hasChildren && state.expanded,
          'selected': state.selected,
          'disabled': state.disabled,
          'dragging': state.dragging,
          'draggable': state.draggable,
          'checked': state.checked,
          'indeterminate': state.indeterminate
        }

        const markerMethods = [
            'weeksInList',
            'important',
            'finalizing',
            'canBeDoneOutsideOfWork',
            'canBePostponed',
            'postponedFor',
            'madeProgress',
        ];

        markerMethods.forEach(name => {
            classes[name] = !!this.node.data.meaningfulMarkers[name]
        })

        const store = this.tree?.vm?.$store
        if (store) {
          const matches = store.getters.nodeFilterMatches.get(this.node.id)
          if (matches) {
            for (const mode of matches.descendants) {
              classes[`has-children-${mode}`] = true
            }
            const active = store.state.filterMode
            if (active !== 'all') {
              classes['filter-hidden'] = !matches.self.has(active) && !matches.descendants.has(active)
            }
          }
        }

        return classes
      }
    },

    methods: {
      onNodeFocus() {
        this.tree.activeElement = this.node
      },

      focus() {
        this.$refs.anchor.focus()
        this.node.select()
      },

      check() {
        if (this.node.checked()) {
          this.node.uncheck()
        } else {
          this.node.check()
        }
      },

      select({ctrlKey} = evnt) {
        const tree = this.tree
        const node = this.node

        tree.$emit('node:clicked', node)

        if (node.isEditing) {
          return
        }

        if (node.editable()) {
          return this.startEditing()
        }

        // For nodes which has a children list we have to expand/collapse
        if (this.hasChildren()) {
          this.toggleExpand()
        }

        if (!node.selected()) {
          node.select(ctrlKey)
        } else {
          if (ctrlKey) {
            node.unselect()
          } else {
            if (this.tree.selectedNodes.length != 1) {
              tree.unselectAll()
              node.select()
            }
          }
        }
      },

      openMenu($event){
          this.menu().open($event, {
              node: this.node
          })
      },

      toggleExpand() {
        if (this.hasChildren()) {
          this.node.toggleExpand()
        }
      },

      hasChildren() {
        return this.node.hasChildren()
      },

      startEditing() {
        if (this.tree._editingNode) {
          this.tree._editingNode.stopEditing()
        }

        this.node.startEditing()
      },

      stopEditing() {
        this.node.stopEditing()
      },

      handleMouseDown(event) {
        this.tree.vm.startDragging(this.node, event)
      }
    }
  }

  export default TreeNode
</script>

