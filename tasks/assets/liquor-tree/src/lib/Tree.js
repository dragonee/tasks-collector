import { markRaw, reactive } from 'vue'

import Node from './Node'
import Emitter from './Emitter'

import objectToNode, { parse } from '../utils/objectToNode'
import { List } from '../utils/stack'
import { recurseDown } from '../utils/recurse'

export default class Tree {
  constructor (vm) {
    this.vm = vm
    this.options = vm.opts

    this.activeElement = null
    this.emitter = new Emitter()

    // Nodes hold a back-reference to the tree; keep the tree itself out of
    // Vue's reactivity so reading node.tree always yields this raw instance.
    markRaw(this)
  }

  $on (name, ...args) {
    this.emitter.$on(name, ...args)
  }

  $once (name, ...args) {
    this.emitter.$once(name, ...args)
  }

  $off (name, ...args) {
    this.emitter.$off(name, ...args)
  }

  $emit (name, ...args) {
    if (this.__silence) {
      return
    }

    this.emitter.$emit(name, ...args)

    if (name !== 'LIQUOR_NOISE') {
      this.emitter.$emit('LIQUOR_NOISE')
    }
  }

  setModel (data) {
    // The tree and the component must share one identity for the model: nodes
    // are already reactive proxies (see objectToNode), and the array is made
    // reactive here so splices done through the tree re-render the component.
    this.model = reactive(this.parse(data))

    /* eslint-disable */
    requestAnimationFrame(_ => {
      this.vm.model = this.model
    })
    /* eslint-enable */

    this.selectedNodes = new List()
    this.checkedNodes = new List()

    recurseDown(this.model, node => {
      node.tree = this

      // Store-driven rebuilds replace every Node instance; carry an
      // in-progress edit over to the node's replacement, matched by id.
      if (this._editingNode && node.id === this._editingNode.id) {
        node.isEditing = true
        this._editingNode = node
        this.activeElement = node
      }

      if (node.selected()) {
        this.selectedNodes.add(node)
      }

      if (node.checked()) {
        this.checkedNodes.add(node)

        if (node.parent) {
          node.parent.refreshIndeterminateState()
        }
      }

      if (node.disabled()) {
        node.recurseDown(child => {
          child.state('disabled', true)
        })
      }
    })
  }

  recurseDown (node, fn) {
    if (!fn && node) {
      fn = node
      node = this.model
    }

    if (typeof fn !== 'function') {
      new TypeError('Argument must be a function')
    }

    return recurseDown(node, fn)
  }

  select (node, extendList) {
    if (extendList) {
      this.selectedNodes.add(node)
    } else {
      this.unselectAll()
      this.selectedNodes
        .empty()
        .add(node)
    }

    return true
  }

  unselect (node) {
    this.selectedNodes.remove(node)

    return true
  }

  unselectAll () {
    let node

    while (node = this.selectedNodes.pop()) {
      node.unselect()
    }

    return true
  }

  check (node) {
    this.checkedNodes.add(node)
  }

  uncheck (node) {
    this.checkedNodes.remove(node)
  }

  index (node, verbose) {
    let target = node.parent

    if (target) {
      target = target.children
    } else {
      target = this.model
    }

    const index = target.indexOf(node)

    if (verbose) {
      return {
        index: index,
        target,
        node: target[index]
      }
    }

    return index
  }

  nextNode (node) {
    const { target, index } = this.index(node, true)

    return target[index + 1] || null
  }

  nextVisibleNode (node) {
    if (node.hasChildren() && node.expanded()) {
      return node.first()
    }

    const nextNode = this.nextNode(node)

    if (!nextNode && node.parent) {
      return node.parent.next()
    }

    return nextNode
  }

  prevNode (node) {
    const { target, index } = this.index(node, true)

    return target[index - 1] || null
  }

  prevVisibleNode (node) {
    const prevNode = this.prevNode(node)

    if (!prevNode) {
      return node.parent
    }

    if (prevNode.hasChildren() && prevNode.expanded()) {
      return prevNode.last()
    }

    return prevNode
  }

  addToModel (node, index = this.model.length) {
    node = this.objectToNode(node)

    this.model.splice(index, 0, node)
    this.recurseDown(node, n => {
      n.tree = this
    })

    this.$emit('node:added', node)

    return node
  }

  append (targetNode, node) {
    return targetNode.append(node)
  }

  prepend (targetNode, node) {
    return targetNode.prepend(node)
  }

  before (targetNode, sourceNode) {
    const position = this.index(targetNode, true)
    const node = this.objectToNode(sourceNode)

    if (!~position.index) {
      return false
    }

    position.target.splice(
      position.index,
      0,
      node
    )

    node.parent = targetNode.parent
    this.$emit('node:added', node)

    return node
  }

  after (targetNode, sourceNode) {
    const position = this.index(targetNode, true)
    const node = this.objectToNode(sourceNode)

    if (!~position.index) {
      return false
    }

    position.target.splice(
      position.index + 1,
      0,
      node
    )

    node.parent = targetNode.parent
    this.$emit('node:added', node)

    return node
  }

  removeNode (node) {
    if (!node) {
      return false
    }

    if (!node.parent) {
      if (~this.model.indexOf(node)) {
        this.model.splice(
          this.model.indexOf(node),
          1
        )
      }
    } else {
      const children = node.parent.children

      if (~children.indexOf(node)) {
        children.splice(
          children.indexOf(node),
          1
        )
      }
    }

    if (node.parent) {
      if (node.parent.indeterminate() && !node.parent.hasChildren()) {
        node.parent.state('indeterminate', false)
      }
    }

    if (this.activeElement !== null) {
      if (node.id === this.activeElement.id) {
        this.activeElement = null
      }
    }

    node.parent = null

    this.$emit('node:removed', node)

    this.selectedNodes.remove(node)
    this.checkedNodes.remove(node)

    return node
  }

  isNode (node) {
    return node instanceof Node
  }

  getNodeById (id) {
    let targetNode = null

    recurseDown(this.model, node => {
      if ('' + node.id === id) {
        targetNode = node
        return false
      }
    })

    return targetNode
  }

  objectToNode (obj) {
    return objectToNode(this, obj)
  }

  parse (data) {
    try {
      return parse(data, this)
    } catch (e) {
      console.error(e)
      return []
    }
  }
}
