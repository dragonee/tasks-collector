/**
 * Minimal event emitter with Vue 2 instance-event semantics ($on/$once/$off/
 * $emit, variadic payloads). Vue 3 removed these from component instances;
 * the Tree keeps its event API by delegating here instead of to its vm.
 */
export default class Emitter {
  constructor () {
    this._listeners = new Map()
  }

  $on (name, fn) {
    if (!this._listeners.has(name)) {
      this._listeners.set(name, [])
    }

    this._listeners.get(name).push(fn)

    return this
  }

  $once (name, fn) {
    const wrapper = (...args) => {
      this.$off(name, wrapper)
      fn(...args)
    }

    return this.$on(name, wrapper)
  }

  $off (name, fn) {
    if (!fn) {
      this._listeners.delete(name)
      return this
    }

    const listeners = this._listeners.get(name)

    if (listeners) {
      const index = listeners.indexOf(fn)

      if (index !== -1) {
        listeners.splice(index, 1)
      }
    }

    return this
  }

  $emit (name, ...args) {
    const listeners = this._listeners.get(name)

    if (listeners) {
      listeners.slice().forEach(fn => fn(...args))
    }

    return this
  }
}
