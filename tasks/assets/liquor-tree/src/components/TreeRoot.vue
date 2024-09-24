<template>
  <component :is="tag" role="tree" :class="{'tree': true, 'tree-loading': this.loading, 'tree--draggable' : !!this.draggableNode}">
    <template v-if="filter && matches.length == 0" >
      <div class="tree-filter-empty" v-html="opts.filter.emptyText"></div>
    </template>
    <template v-else>
      <ul class="tree-root" @dragstart="onDragStart">
        <template v-if="opts.filter.plainList && matches.length > 0">
          <TreeNode
            v-for="node in matches"
            v-if="node.visible()"

            :key="node.id"
            :node="node"
            :options="opts"
          />
        </template>
        <template v-else>
          <TreeNode
            v-for="node in model"
            v-if="node && node.visible()"

            :key="node.id"
            :node="node"
            :options="opts"
          />
        </template>
      </ul>
    </template>

    <vue-context ref="menu">
        <template slot-scope="child">
           <li class="v-context__sub">
                <a>Importance</a>
                <ul class="v-context v-context-inline">
                    <li>
                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 1 })">1</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 2 })">2</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 3 })">3</a>

                         <a href="#" @click.prevent="onClick('important', {... child.data, value: 0 })">Reset</a>
                    </li>
                </ul>
            </li>

            <li>
                <a href="#" @click.prevent="onClick('finalizing', { ...child.data  })">Clearable</a>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('madeProgress', { ...child.data  })">Made progress</a>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('canBePostponed', { ...child.data  })">⟳ Repeat</a>
            </li>

            <li class="v-context__sub">
                 <a>Postpone for</a>
                 <ul class="v-context v-context-inline">
                     <li>
                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 1 })">1</a>

                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 2 })">2</a>

                          <a href="#" @click.prevent="onClick('postponedFor', {... child.data, value: 3 })">3</a>
                     </li>
                 </ul>
             </li>

             <li class="v-context__sub" v-if="currentThread">
                <a>Move to</a>

                <ul class="v-context">
                    <li>
                        <a href="#" v-if="currentThread.name != 'Sidetrack'" @click.prevent="onClick('transition', {... child.data, value: 'Sidetrack' })">Sidetrack</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name != 'Daily'" @click.prevent="onClick('transition', {... child.data, value: 'Daily' })">Daily</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name == 'Books'" @click.prevent="onClick('transition', {... child.data, value: 'Read' })">Read (backlog)</a>
                    </li>
                    <li>
                        <a href="#" v-if="currentThread.name != 'Trash'" @click.prevent="onClick('transition', {... child.data, value: 'Trash' })">🗑 Trash</a>
                    </li>
                    <li>
                        <a href="#" @click.prevent="onClick('transition', {... child.data, value: UNSET })">Clear</a>
                    </li>
                </ul>
            </li>
            <li>
                <a href="#" @click.prevent="onClick('remove', { ...child.data  })">Remove</a>
            </li>

       </template>
   </vue-context>

    <DraggableNode v-if="draggableNode" :target="draggableNode" />
  </component>
</template>

<script>
  import TreeNode from './TreeNode'
  import DraggableNode from './DraggableNode'
  import TreeMixin from '../mixins/TreeMixin'
  import TreeDnd from '../mixins/DndMixin'
  import Tree from '../lib/Tree'

  import { VueContext }from 'vue-context';

  import { mapGetters } from 'vuex';

  const UNSET = '__UNSET';

  const defaults = {
    direction: 'ltr',
    multiple: true,
    checkbox: false,
    checkOnSelect: false,
    autoCheckChildren: true,
    autoDisableChildren: true,
    checkDisabledChildren: true,
    parentSelect: false,
    keyboardNavigation: true,
    nodeIndent: 24,
    minFetchDelay: 0,
    fetchData: null,
    propertyNames: null,
    deletion: false,
    dnd: false,
    editing: false,
    onFetchError: function(err) { throw err }
  }

  const changeMeaningfulMarker = (data, object) => ({
      ...data,
      meaningfulMarkers: {
          ...data.meaningfulMarkers,
          ...object,
      }
  });

  const clearMeaningfulMarker = (data, key) => {
      let markers = {...data.meaningfulMarkers}

      delete markers[key]

      return {
          ...data,
          meaningfulMarkers: markers,
      };
  };

  const filterDefaults = {
    emptyText: 'Nothing found!',
    matcher(query, node) {
      const isMatched = new RegExp(query, 'i').test(node.text)

      if (isMatched) {
        if (node.parent && new RegExp(query, 'i').test(node.parent.text)) {
          return false
        }
      }

      return isMatched
    },
    plainList: false,
    showChildren: true
  }

  export default {
    name: 'Tree',
    components: {
      TreeNode,
      DraggableNode,
      VueContext
    },

    mixins: [TreeMixin, TreeDnd],

    provide() {
        return {
            tree: null,
            menu: () => this.$refs.menu,
        }
    },

    props: {
      data: {},

      options: {
        type: Object,
        default: _ => ({})
      },

      filter: String,

      tag: {
        type: String,
        default: 'div'
      }
    },

    watch: {
      filter (term) {
        this.tree.filter(term)
      }
    },

    methods: {
        async onClick(method, { node, value }) {
            const markerMethods = [
                'weeksInList',
                'important',
                'finalizing',
                'canBeDoneOutsideOfWork',
                'canBePostponed',
                'postponedFor',
                'madeProgress',
                'transition',
            ];

            if (markerMethods.includes(method)) {
                if (value === undefined) {
                    value = !node.data.meaningfulMarkers[method]
                }

                if (value === UNSET) {
                    node.data = clearMeaningfulMarker(node.data, method)
                } else {
                    node.data = changeMeaningfulMarker(node.data, {
                        [method]: value
                    })
                }

                if (method === 'postponedFor') {
                    node.hide()
                }

                this.$emit('LIQUOR_NOISE')
            } else if (method === 'remove') {
                node.remove()
            }
        }
    },

    computed: {
        ...mapGetters(['currentThread']),
    },

    data () {
      // we should not mutating a prop directly...
      // that's why we have to create a new object
      // TODO: add method for changing options
      let opts = Object.assign({}, defaults, this.options)

      opts.filter = Object.assign(
        {},
        filterDefaults,
        opts.filter
      )

      return {
        model: null,
        tree: null,
        loading: false,
        opts,
        matches: [],
        draggableNode: null,
        UNSET,
      }
    }
  }
</script>

