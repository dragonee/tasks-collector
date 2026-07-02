import { ref } from 'vue'

const DropPosition = {
  ABOVE: 'drag-above',
  BELOW: 'drag-below',
  ON: 'drag-on'
}

function isMovingStarted (event, start) {
  return Math.abs(event.clientX - start[0]) > 5 || Math.abs(event.clientY - start[1]) > 5
}

function composedPath (event) {
  let el = event.target
  const path = []

  while (el) {
    path.push(el)

    if (el.tagName === 'HTML') {
      path.push(document)
      path.push(window)

      return path
    }

    el = el.parentElement
  }

  return path
}

function getPath (event) {
  if (event.path) {
    return event.path
  }

  if (event.composedPath) {
    return event.composedPath()
  }

  return composedPath(event)
}

function getSelectedNode (event) {
  let className
  let i = 0

  const path = getPath(event)

  for (; i < path.length; i++) {
    className = path[i].className || ''

    if (/tree-node/.test(className)) {
      return path[i]
    }
  }

  return null
}

function getDropDestination (e) {
  const selectedNode = getSelectedNode(e)

  if (!selectedNode) {
    return null
  }

  return selectedNode
}

function getLastRootNodeElement ($el) {
  const nodes = $el.querySelectorAll('.tree-root > .tree-node')

  return nodes.length ? nodes[nodes.length - 1] : null
}

function isBelowElement (e, element) {
  const coords = element.getBoundingClientRect()

  return e.clientY > coords.bottom &&
    e.clientX >= coords.left &&
    e.clientX <= coords.right
}

function updateHelperClasses (target, classes) {
  if (!target) {
    return
  }

  let className = target.className

  if (!classes) {
    for (const i in DropPosition) {
      className = className.replace(DropPosition[i], '')
    }

    className.replace('dragging', '')
  } else if (!new RegExp(classes).test(className)) {
    className += ' ' + classes
  }

  target.className = className.replace(/\s+/g, ' ')
}

function getDropPosition (e, element) {
  const coords = element.getBoundingClientRect()
  const nodeSection = coords.height / 3

  let dropPosition = DropPosition.ON

  if (coords.top + nodeSection >= e.clientY) {
    dropPosition = DropPosition.ABOVE
  } else if (coords.top + nodeSection * 2 <= e.clientY) {
    (
      dropPosition = DropPosition.BELOW
    )
  }

  return dropPosition
}

function clearDropClasses (parent) {
  for (const key in DropPosition) {
    const el = parent.querySelectorAll(`.${DropPosition[key]}`)

    for (let i = 0; i < el.length; i++) {
      updateHelperClasses(el[i])
    }
  }
}

export default function useDnd ({ tree, el }) {
  const draggableNode = ref(null)

  let startDragPosition = null
  let possibleDragNode = null
  let dropDestination = null

  function onDragStart (e) {
    e.preventDefault()
  }

  function startDragging (node, event) {
    if (!node.isDraggable()) {
      return
    }

    startDragPosition = [event.clientX, event.clientY]
    possibleDragNode = node

    initDragListeners()
  }

  function initDragListeners () {
    let dropPosition

    const removeListeners = () => {
      window.removeEventListener('mouseup', onMouseUp, true)
      window.removeEventListener('mousemove', onMouseMove, true)
    }

    const onMouseUp = (e) => {
      if (!startDragPosition) {
        e.stopPropagation()
      }

      if (draggableNode.value) {
        draggableNode.value.node.state('dragging', false)
      }

      if (dropDestination && tree.value.isNode(dropDestination) && dropDestination.vm) {
        updateHelperClasses(dropDestination.vm.$el, null)

        if (!(!dropDestination.isDropable() && dropPosition === DropPosition.ON || !dropPosition)) {
          draggableNode.value.node.finishDragging(dropDestination, dropPosition)
          draggableNode.value.node.parent = dropDestination
        }

        dropDestination = null
      }

      possibleDragNode = null
      draggableNode.value = null

      removeListeners()
    }

    const onMouseMove = (e) => {
      if (startDragPosition && !isMovingStarted(e, startDragPosition)) {
        return
      } else {
        startDragPosition = null
      }

      if (possibleDragNode) {
        if (possibleDragNode.startDragging() === false) {
          removeListeners()
          possibleDragNode = null

          return
        }

        draggableNode.value = { node: possibleDragNode, left: 0, top: 0 }
        possibleDragNode = null
      }

      draggableNode.value.left = e.clientX
      draggableNode.value.top = e.clientY

      const dropDestinationElement = getDropDestination(e)

      clearDropClasses(el.value)

      if (dropDestinationElement) {
        const dropDestinationId = dropDestinationElement.getAttribute('data-id')

        if (draggableNode.value.node.id === dropDestinationId) {
          return
        }

        if (!dropDestination || dropDestination.id !== dropDestinationId) {
          dropDestination = tree.value.getNodeById(dropDestinationId)
        }

        if (dropDestination && draggableNode.value.node) {
          const path = dropDestination.getPath()

          if (path.includes(draggableNode.value.node)) {
            dropDestination = null
            return
          }
        }

        dropPosition = getDropPosition(e, dropDestinationElement)

        const isDropable = dropDestination.isDropable()

        if (!isDropable && dropPosition === DropPosition.ON) {
          dropPosition = null
        }

        updateHelperClasses(dropDestinationElement, dropPosition)
      } else {
        // No node under the cursor. Below the last root node this means
        // dragging past the end of the board — treat it as a drop after
        // that node at root level, so an item can leave the last subtree.
        const lastRootElement = getLastRootNodeElement(el.value)

        if (lastRootElement && isBelowElement(e, lastRootElement)) {
          const lastRootId = lastRootElement.getAttribute('data-id')

          if (draggableNode.value.node.id === lastRootId) {
            return
          }

          dropDestination = tree.value.getNodeById(lastRootId)
          dropPosition = DropPosition.BELOW

          updateHelperClasses(lastRootElement, dropPosition)
        }
      }
    }

    window.addEventListener('mouseup', onMouseUp, true)
    window.addEventListener('mousemove', onMouseMove, true)
  }

  return { draggableNode, onDragStart, startDragging }
}
