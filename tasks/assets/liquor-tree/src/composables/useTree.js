import { onMounted, nextTick, ref, shallowRef } from 'vue'

import Tree from '../lib/Tree'
import initKeyboardNavigation from '../utils/keyboardNavigation'

export default function useTree ({ opts, emit, el, startDragging }) {
  const model = ref(null)
  const tree = shallowRef(null)

  // The Tree class, keyboardNavigation and TreeNode all reach back into the
  // component through `tree.vm` — this facade provides the surface the
  // options-API instance used to expose.
  const vm = {
    opts,
    $emit: emit,
    startDragging,
    get model () { return model.value },
    set model (value) { model.value = value },
    get $el () { return el.value },
  }

  function connectStore (store) {
    const { store: Store, getter, dispatcher } = store

    Store.$subscribe(() => {
      tree.value.setModel(getter())
    })

    tree.value.setModel(getter())

    // assigned after the initial setModel so parsing the current store
    // state never dispatches it straight back
    tree.value._syncStore = () => {
      nextTick(() => {
        dispatcher(toJSON())
      })
    }
  }

  function append (criteria, node) {
    // append to model
    if (!node) {
      return tree.value.addToModel(criteria, tree.value.model.length)
    }

    return tree.value.append(criteria, node)
  }

  function prepend (criteria, node) {
    if (!node) {
      return tree.value.addToModel(criteria, 0)
    }

    return tree.value.prepend(criteria, node)
  }

  function addChild (criteria, node) {
    return append(criteria, node)
  }

  function remove (node) {
    return tree.value.removeNode(node)
  }

  function before (criteria, node) {
    if (!node) {
      return prepend(criteria)
    }

    return tree.value.before(criteria, node)
  }

  function after (criteria, node) {
    if (!node) {
      return append(criteria)
    }

    return tree.value.after(criteria, node)
  }

  function toJSON () {
    return JSON.parse(
      JSON.stringify(model.value)
    )
  }

  onMounted(() => {
    const instance = new Tree(vm)

    // `tree` is provided to every TreeNode as this shallowRef, so setting it
    // here late-binds the injection.
    tree.value = instance

    connectStore(opts.store)

    emit('tree:mounted', vm)

    initKeyboardNavigation(instance)
  })

  return { tree, model, append, prepend, addChild, remove, before, after, toJSON }
}
