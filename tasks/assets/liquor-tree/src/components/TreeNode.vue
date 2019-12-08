<template>
  <li class="tree-node" :data-id="node.id" :class="nodeClass" @mousedown.stop="handleMouseDown" @contextmenu.stop.prevent="openMenu">
    <div class="tree-content" :style="[options.direction == 'ltr' ? {'padding-left': padding} : {'padding-right': padding}]" @click="select">
      <i
        class="tree-arrow"
        :class="[{'expanded': node.states.expanded, 'has-child': node.children.length || node.isBatch}, options.direction]"
        @click.stop="toggleExpand">
      </i>

      <i
        v-if="options.checkbox"
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

      return {
        loading: false
      }
    },

    computed: {
      padding() {
        return this.node.depth * (this.options.paddingLeft ? this.options.paddingLeft : this.options.nodeIndent) + 'px'
      },

      nodeClass() {
        let state = this.node.states
        let hasChildren = this.hasChildren()
        let classes = {
          'has-child': hasChildren,
          'expanded': hasChildren && state.expanded,
          'selected': state.selected,
          'disabled': state.disabled,
          'matched': state.matched,
          'dragging': state.dragging,
          'loading': this.loading,
          'draggable': state.draggable
        }

        if (this.options.checkbox) {
          classes['checked'] = state.checked
          classes['indeterminate'] = state.indeterminate
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
        const opts = this.options
        const tree = this.tree
        const node = this.node

        tree.$emit('node:clicked', node)

        if (opts.editing && node.isEditing) {
          return
        }

        if (opts.editing && node.editable()) {
          return this.startEditing()
        }

        if (opts.checkbox && opts.checkOnSelect) {
          if (!opts.parentSelect && this.hasChildren()) {
            return this.toggleExpand()
          }

          return this.check(ctrlKey)
        }

        // 'parentSelect' behaviour.
        // For nodes which has a children list we have to expand/collapse
        if (!opts.parentSelect && this.hasChildren()) {
          this.toggleExpand()
        }

        if (opts.multiple) {
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
        } else {
          if (node.selected() && ctrlKey) {
            node.unselect()
          } else {
            node.select()
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
        if (!this.options.dnd) {
          return
        }

        this.tree.vm.startDragging(this.node, event)
      }
    }
  }

  export default TreeNode
</script>

