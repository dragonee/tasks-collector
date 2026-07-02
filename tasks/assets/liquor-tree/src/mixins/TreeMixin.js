import Tree from '../lib/Tree'
import initKeyboardNavigation from '../utils/keyboardNavigation'

export default {
  mounted () {
    const tree = new Tree(this)

    // TreeRoot provides `tree` as a computed over this data property, so
    // setting it here late-binds the injection in every TreeNode.
    this.tree = tree

    this.connectStore(this.opts.store)

    this.$emit('tree:mounted', this)

    initKeyboardNavigation(tree)
  },

  methods: {
    connectStore (store) {
      const { store: Store, getter, dispatcher } = store

      Store.$subscribe(() => {
        this.tree.setModel(getter())
      })

      this.tree.setModel(getter())

      // assigned after the initial setModel so parsing the current store
      // state never dispatches it straight back
      this.tree._syncStore = () => {
        this.$nextTick(_ => {
          dispatcher(this.toJSON())
        })
      }
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

    remove (node) {
      return this.tree.removeNode(node)
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

    toJSON () {
      return JSON.parse(
        JSON.stringify(this.model)
      )
    }
  }

/*eslint semi: 0 */
/* https://github.com/vuejs/rollup-plugin-vue/issues/169 */
};
