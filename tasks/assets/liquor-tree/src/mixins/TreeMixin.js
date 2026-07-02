import Tree from '../lib/Tree'
import initKeyboardNavigation from '../utils/keyboardNavigation'
import assert from '../utils/assert'

function initEvents (vm) {
  const tree = vm.tree

  tree.$on('node:added', (targetNode, newNode) => {
    const node = newNode || targetNode

    if (node.state('checked') && !tree.checkedNodes.has(node)) {
      tree.checkedNodes.add(node)
    }

    node.refreshIndeterminateState()

    if (node.state('selected') && !tree.selectedNodes.has(node)) {
      tree.select(node)
    }
  })
}

export default {
  mounted () {
    const tree = new Tree(this)

    this.tree = tree
    this._provided.tree = tree

    this.connectStore(this.opts.store)

    this.$emit('tree:mounted', this)

    initEvents(this)

    initKeyboardNavigation(tree)
  },

  methods: {
    connectStore (store) {
      const { store: Store, mutations, getter, dispatcher } = store

      assert(typeof getter === 'function', '`getter` must be a function')
      assert(typeof dispatcher === 'function', '`dispatcher` must be a function')

      if (undefined !== mutations) {
        assert(Array.isArray(mutations), '`mutations` must be an array')
      }

      Store.subscribe((action, state) => {
        if (!mutations) {
          this.tree.setModel(getter())
        } else if (mutations.includes(action.type)) {
          this.tree.setModel(getter())
        }
      })

      this.tree.setModel(getter())

      this.$on('LIQUOR_NOISE', () => {
        this.$nextTick(_ => {
          dispatcher(this.toJSON())
        })
      })
    },

    append (criteria, node) {
      // append to model
      if (!node) {
        return this.tree.addToModel(criteria, this.tree.model.length)
      }

      return this.tree.append(criteria, node)
    },

    prepend (criteria, node) {
      if (!node) {
        return this.tree.addToModel(criteria, 0)
      }

      return this.tree.prepend(criteria, node)
    },

    addChild (criteria, node) {
      return this.append(criteria, node)
    },

    remove (criteria, multiple) {
      return this.tree.remove(criteria, multiple)
    },

    before (criteria, node) {
      if (!node) {
        return this.prepend(criteria)
      }

      return this.tree.before(criteria, node)
    },

    after (criteria, node) {
      if (!node) {
        return this.append(criteria)
      }

      return this.tree.after(criteria, node)
    },

    find (criteria, multiple) {
      return this.tree.find(criteria, multiple)
    },

    toJSON () {
      return JSON.parse(
        JSON.stringify(this.model)
      )
    }
  }

/*eslint semi: 0 */
/* https://github.com/vuejs/rollup-plugin-vue/issues/169 */
};
