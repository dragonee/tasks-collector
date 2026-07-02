import Node from '../lib/Node'
import uuidV4 from './uuidV4'

/**
* Default Node's states
*/
const nodeStates = {
  selected: false,
  selectable: true,
  checked: false,
  expanded: false,
  disabled: false,
  visible: true,
  indeterminate: false,
  editable: true,
  dragging: false,
  draggable: true,
  dropable: true
}

function merge (state = {}) {
  return Object.assign({}, nodeStates, state)
}

/**
  Every Node has certain format:
  {
    id,           // Unique Node id. By default it generates using uuidV4
    text,         // Node text
    children,     // List of children. Each children has the same format
    parent,       // Parent Node or null. The tree is able to have more than 1 root node
    state,        // States of Node. Ex.: selected, checked and so on
    data          // Any types of data. Ex.: data: {myAwesomeProperty: 10}
  }
*/
export function parse (data, tree) {
  if (typeof data === 'string') {
    data = JSON.parse(data)
  }

  if (!Array.isArray(data)) {
    data = [data]
  }

  return data.map(item => objectToNode(tree, item))
}

export default function objectToNode (tree, obj) {
  let node = null

  if (obj instanceof Node) {
    return obj
  }

  if (typeof obj === 'string') {
    node = new Node(tree, {
      text: obj,
      state: merge(),
      id: uuidV4()
    })
  } else if (Array.isArray(obj)) {
    return obj.map(o => objectToNode(tree, o))
  } else {
    node = new Node(tree, obj)
    node.states = merge(node.states)

    if (!node.id) {
      node.id = uuidV4()
    }

    if (node.children.length) {
      node.children = node.children.map(child => {
        child = objectToNode(tree, child)
        child.parent = node

        return child
      })
    }
  }

  return node
}
