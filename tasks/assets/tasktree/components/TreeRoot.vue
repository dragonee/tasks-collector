<template>
  <div role="tree" ref="el" :class="{'tree': true, 'tree--draggable' : !!draggableNode}">
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

<script setup>
  import { computed, provide, ref } from 'vue'

  import TreeNode from './TreeNode.vue'
  import DraggableNode from './DraggableNode.vue'
  import ContextMenu from './ContextMenu.vue'
  import useTree from '../composables/useTree'
  import useDnd from '../composables/useDnd'

  import { Notifier } from '../../notifier';
  import { MEANINGFUL_MARKER_KEYS } from '../../utils.js';

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

  const props = defineProps({
    options: {
      type: Object,
      default: _ => ({})
    }
  })

  // every event Tree.$emit forwards to the component emit; Vue warns on any
  // emitted event that is not declared here
  const emit = defineEmits([
      'tree:mounted',
      'node:added',
      'node:removed',
      'node:clicked',
      'node:dblclick',
      'node:selected',
      'node:unselected',
      'node:checked',
      'node:unchecked',
      'node:expanded',
      'node:collapsed',
      'node:shown',
      'node:hidden',
      'node:enabled',
      'node:disabled',
      'node:dragging:start',
      'node:dragging:finish',
      'node:editing:start',
      'node:editing:stop',
      'node:text:changed',
  ])

  // we should not mutate the options prop directly, so merge it once
  // into a local object
  const opts = { ...defaults, ...props.options }

  const el = ref(null)
  const menu = ref(null)

  const { tree, model, append, prepend, addChild, remove, before, after, toJSON } = useTree({
    opts,
    emit,
    el,
    // late-bound: the dnd wiring happens right below
    startDragging: (node, event) => startDragging(node, event),
  })

  const { draggableNode, onDragStart, startDragging } = useDnd({ tree, el })

  // the Tree instance only exists after mounted; the shallowRef late-binds
  // it for the injecting TreeNodes
  provide('tree', tree)
  provide('menu', () => menu.value)

  const currentThread = computed(() => opts.store?.store?.currentThread ?? null)

  const visibleNodes = computed(() => (model.value || []).filter(node => node && node.visible()))

  async function onClick(method, { node, value }) {
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

          tree.value.syncStore()
      } else if (method === 'addToPlan') {
          const taskText = node.data.text
          const timeframe = value  // 'today', 'tomorrow', 'this_week'
          const notifier = Notifier({ time: 3000 })

          try {
              const response = await fetch('/plans/add-task/', {
                  method: 'POST',
                  headers: {
                      'Content-Type': 'application/json',
                      'X-CSRFToken': getCsrfToken(),
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
  }

  function getCsrfToken() {
      const token = document.body.querySelector('[name=csrfmiddlewaretoken]')
      return token ? token.value : ''
  }

  defineExpose({ tree, append, prepend, addChild, remove, before, after, toJSON })
</script>
