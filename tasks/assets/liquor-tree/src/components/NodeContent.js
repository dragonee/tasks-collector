import { h, nextTick } from 'vue'

const NodeContent = {
  name: 'node-content',
  props: ['node'],
  render () {
    const node = this.node
    const vm = this.node.tree.vm
    const slots = vm.$slots

    if (node.isEditing) {
      let nodeText = node.text

      nextTick(() => {
        if (this.$refs.editCtrl) {
          this.$refs.editCtrl.focus()
        }
      })

      return h('input', {
        value: node.text,
        type: 'text',
        class: 'tree-input',
        onInput: (e) => {
          nodeText = e.target.value
        },
        onBlur: () => {
          node.stopEditing(nodeText)
        },
        onKeyup: (e) => {
          if (e.keyCode === 13) {
            node.stopEditing(nodeText)
          }
        },
        onMouseup: (e) => {
          e.stopPropagation()
        },
        ref: 'editCtrl'
      })
    }

    if (slots.default) {
      return slots.default({ node: this.node })
    }

    return h('span', {
      innerHTML: node.text
    })
  }
}

export default NodeContent
