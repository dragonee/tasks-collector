<template>
  <ul
    v-show="visible"
    ref="el"
    class="v-context"
    :style="{ top: top + 'px', left: left + 'px' }"
    @contextmenu.prevent
  >
    <slot :data="data"></slot>
  </ul>
</template>

<script setup>
  /**
   * Replacement for vue-context (Vue 2 only): same .v-context markup contract
   * and the open(event, data)/close() API the tree uses. The menu closes on
   * any document click — including its own items, after their handlers run —
   * and on Escape. Submenus open on :hover (see styles/_context-menu.scss).
   */
  import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

  const el = ref(null)

  const visible = ref(false)
  const data = ref(null)
  const top = ref(0)
  const left = ref(0)

  let openedAt = 0

  function open (event, payload) {
    data.value = payload
    visible.value = true
    left.value = event.clientX
    top.value = event.clientY
    openedAt = event.timeStamp

    nextTick(() => {
      // keep the menu inside the viewport
      if (left.value + el.value.offsetWidth > window.innerWidth) {
        left.value = Math.max(0, window.innerWidth - el.value.offsetWidth)
      }

      if (top.value + el.value.offsetHeight > window.innerHeight) {
        top.value = Math.max(0, window.innerHeight - el.value.offsetHeight)
      }
    })
  }

  function close () {
    visible.value = false
    data.value = null
  }

  function onDocumentClick (event) {
    // a ctrl+click gesture (macOS) fires a click alongside the
    // contextmenu that opened the menu; ignore it
    if (event.timeStamp - openedAt < 100) {
      return
    }

    close()
  }

  function onKeyup (event) {
    if (event.key === 'Escape') {
      close()
    }
  }

  onMounted(() => {
    document.addEventListener('click', onDocumentClick)
    document.addEventListener('keyup', onKeyup)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('click', onDocumentClick)
    document.removeEventListener('keyup', onKeyup)
  })

  defineExpose({ open, close })
</script>
