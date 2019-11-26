<template>
  <div class="tree-dragnode" :style="style">
    {{ target.node.text }}
  </div>
</template>

<script>
  export default {
    name: 'DragNode',
    props: ['target'],
    computed: {
      style() {
        if (undefined === this.target.top) {
          return 'display: none'
        }

        return `top: ${this.target.top}px; left: ${this.target.left}px`
      }
    }
  }
</script>
