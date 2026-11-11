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
                    <li v-for="thread in moveTargets" :key="thread.id">
                        <a href="#" @click.prevent="onClick('transition', {... child.data, value: thread.name })">{{ moveTargetLabel(thread) }}</a>
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

  // Where an item can be marked to move on commit: every board the user may
  // change (their own threads, then the boards shared with them) but the one
  // shown. A shared board named like one of their own is left out: the commit
  // would pick their own.
  const moveTargets = computed(() => {
      const threads = opts.store?.store?.threads ?? []
      const own = new Set(threads.filter(t => !t.shared_by).map(t => t.name))
      return threads.filter(t =>
          t.id !== currentThread.value?.id && !(t.shared_by && own.has(t.name))
      )
  })

  function moveTargetLabel(thread) {
      if (thread.shared_by) {
          return `${thread.name} (${thread.shared_by})`
      }
      return thread.name === 'Trash' ? '🗑 Trash' : thread.name
  }

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
                      timeframe: timeframe,
                      date: localDate()
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

  // The day it is here, as YYYY-MM-DD. The server's day (UTC) differs from
  // it for part of every night.
  function localDate() {
      const now = new Date()
      const pad = (n) => String(n).padStart(2, '0')
      return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  }

  function getCsrfToken() {
      const token = document.body.querySelector('[name=csrfmiddlewaretoken]')
      return token ? token.value : ''
  }

  defineExpose({ tree, append, prepend, addChild, remove, before, after, toJSON })
</script>
