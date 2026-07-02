<template>
  <li class="tree-node" ref="el" :data-id="node.id" :class="nodeClass" @mousedown.stop="handleMouseDown" @contextmenu.stop.prevent="openMenu">
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
          <input
            v-if="node.isEditing"
            ref="editCtrl"
            class="tree-input"
            type="text"
            :value="node.text"
            @input="editText = $event.target.value"
            @blur="node.stopEditing(editText)"
            @keyup.enter="node.stopEditing(editText)"
            @mouseup.stop
          >
          <NodeContent v-else :node="node" class="tree-text" />
      </span>
    </div>

    <transition name="l-fade">
      <ul
        v-if="hasChildren() && node.states.expanded"
        class="tree-children">
          <TreeNode
            v-for="child in visibleChildren"

            :key="child.id"
            :node="child"
            :options="options"
            >
          </TreeNode>
      </ul>
    </transition>
  </li>
</template>

<script setup>
  import { computed, inject, nextTick, ref, watch } from 'vue'

  import NodeContent from '../../components/NodeContent.vue'
  import { MEANINGFUL_MARKER_KEYS } from '../../utils.js'

  const props = defineProps(['node', 'options'])

  // `tree` is a shallowRef late-bound in TreeRoot's mounted hook (the Tree
  // instance is created there); `menu` is a function returning the ContextMenu
  const tree = inject('tree')
  const menu = inject('menu')

  const el = ref(null)
  const anchor = ref(null)
  const editCtrl = ref(null)

  const editText = ref('')

  // Node methods and the dnd composable reach back into the component
  // through `node.vm` — this facade provides the surface they use.
  const vm = {
    focus,
    get $el () { return el.value },
  }

  props.node.vm = vm

  watch(() => props.node, (node) => {
    node.vm = vm
  })

  watch(() => props.node.isEditing, (isEditing) => {
    if (isEditing) {
      editText.value = props.node.text

      nextTick(() => {
        editCtrl.value && editCtrl.value.focus()
      })
    }
  }, {
    // a freshly appended node can already be in editing state
    immediate: true
  })

  const visibleChildren = computed(() => props.node.children.filter(child => child && child.visible()))

  const padding = computed(() => props.node.depth * props.options.nodeIndent + 'px')

  const nodeClass = computed(() => {
    let state = props.node.states
    let nodeHasChildren = hasChildren()
    let classes = {
      'has-child': nodeHasChildren,
      'expanded': nodeHasChildren && state.expanded,
      'selected': state.selected,
      'disabled': state.disabled,
      'dragging': state.dragging,
      'draggable': state.draggable,
      'checked': state.checked,
      'indeterminate': state.indeterminate
    }

    MEANINGFUL_MARKER_KEYS.forEach(name => {
        classes[name] = !!props.node.data.meaningfulMarkers[name]
    })

    const store = props.options.store?.store
    if (store) {
      const matches = store.nodeFilterMatches.get(props.node.id)
      if (matches) {
        for (const mode of matches.descendants) {
          classes[`has-children-${mode}`] = true
        }
        const active = store.filterMode
        if (active !== 'all') {
          classes['filter-hidden'] = !matches.self.has(active) && !matches.descendants.has(active)
        }
      }
    }

    return classes
  })

  function onNodeFocus() {
    tree.value.activeElement = props.node
  }

  function focus() {
    anchor.value.focus()
    props.node.select()
  }

  function check() {
    if (props.node.checked()) {
      props.node.uncheck()
    } else {
      props.node.check()
    }
  }

  function select({ctrlKey} = {}) {
    const node = props.node

    tree.value.$emit('node:clicked', node)

    if (node.isEditing) {
      return
    }

    if (node.editable()) {
      return startEditing()
    }

    // For nodes which has a children list we have to expand/collapse
    if (hasChildren()) {
      toggleExpand()
    }

    if (!node.selected()) {
      node.select(ctrlKey)
    } else {
      if (ctrlKey) {
        node.unselect()
      } else {
        if (tree.value.selectedNodes.length != 1) {
          tree.value.unselectAll()
          node.select()
        }
      }
    }
  }

  function openMenu($event){
      menu().open($event, {
          node: props.node
      })
  }

  function toggleExpand() {
    if (hasChildren()) {
      props.node.toggleExpand()
    }
  }

  function hasChildren() {
    return props.node.hasChildren()
  }

  function startEditing() {
    if (tree.value._editingNode) {
      tree.value._editingNode.stopEditing()
    }

    props.node.startEditing()
  }

  function stopEditing() {
    props.node.stopEditing()
  }

  function handleMouseDown(event) {
    tree.value.vm.startDragging(props.node, event)
  }

  defineExpose({ focus, startEditing, stopEditing })
</script>
