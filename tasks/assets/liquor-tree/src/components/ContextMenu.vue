<template>
  <ul
    v-show="visible"
    class="v-context"
    :style="{ top: top + 'px', left: left + 'px' }"
    @contextmenu.prevent
  >
    <slot :data="data"></slot>
  </ul>
</template>

<script>
  /**
   * Replacement for vue-context (Vue 2 only): same .v-context markup contract
   * and the open(event, data)/close() API the tree uses. The menu closes on
   * any document click — including its own items, after their handlers run —
   * and on Escape. Submenus open on :hover (see styles/_context-menu.scss).
   */
  export default {
    name: 'ContextMenu',

    data () {
      return {
        visible: false,
        data: null,
        top: 0,
        left: 0
      }
    },

    mounted () {
      document.addEventListener('click', this.onDocumentClick)
      document.addEventListener('keyup', this.onKeyup)
    },

    beforeUnmount () {
      document.removeEventListener('click', this.onDocumentClick)
      document.removeEventListener('keyup', this.onKeyup)
    },

    methods: {
      open (event, data) {
        this.data = data
        this.visible = true
        this.left = event.clientX
        this.top = event.clientY
        this._openedAt = event.timeStamp

        this.$nextTick(() => {
          // keep the menu inside the viewport
          const el = this.$el

          if (this.left + el.offsetWidth > window.innerWidth) {
            this.left = Math.max(0, window.innerWidth - el.offsetWidth)
          }

          if (this.top + el.offsetHeight > window.innerHeight) {
            this.top = Math.max(0, window.innerHeight - el.offsetHeight)
          }
        })
      },

      close () {
        this.visible = false
        this.data = null
      },

      onDocumentClick (event) {
        // a ctrl+click gesture (macOS) fires a click alongside the
        // contextmenu that opened the menu; ignore it
        if (event.timeStamp - this._openedAt < 100) {
          return
        }

        this.close()
      },

      onKeyup (event) {
        if (event.key === 'Escape') {
          this.close()
        }
      }
    }
  }
</script>
