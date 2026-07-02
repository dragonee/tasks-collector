<template>
  <div class="tree-dragnode" :style="style">
    {{ target.node.text }}
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  const props = defineProps(['target'])

  const style = computed(() => {
    if (undefined === props.target.top) {
      return 'display: none'
    }

    return `top: ${props.target.top}px; left: ${props.target.left}px`
  })
</script>
