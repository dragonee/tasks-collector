# Vue 2 to Vue 3 Migration Plan

## Overview

Migrate from Vue 2.7.8 + Vuex 3.6.2 to Vue 3 + Pinia using Composition API.

**Strategy:** Big bang rewrite (not incremental)
**TypeScript:** No (staying with JavaScript)
**Tree Library:** Migrate LiquorTree to Vue 3 (recommended over replacement - preserves custom features)

---

## Phase 1: Dependencies & Build Config

### 1.1 Update package.json

**Remove:**
```
vue ^2.7.8
vuex ^3.6.2
vue-router ^3.6.5
vue-context ^5.2.0
vue-global-events ^1.2.1
@rsbuild/plugin-vue2 ^1.0.4
```

**Add:**
```
vue ^3.5.x
vue-router ^4.x
pinia ^2.x
@imengyu/vue3-context-menu ^1.5.x
mitt ^3.x (for event bus in LiquorTree)
@rsbuild/plugin-vue ^1.x
```

### 1.2 Update rsbuild.config.ts

**File:** `/tasks-collector/rsbuild.config.ts`

- Replace `@rsbuild/plugin-vue2` with `@rsbuild/plugin-vue`

---

## Phase 2: Core Infrastructure

### 2.1 Create Pinia Store

**Create:** `/tasks/assets/stores/boardStore.js`

Convert Vuex store to Pinia using Composition API style:
- State becomes `ref()` variables
- Getters become `computed()`
- Mutations are removed (direct state mutation)
- Actions become regular async functions

**Source:** `/tasks/assets/store.js` (179 lines)

### 2.2 Rewrite App Entry Point

**File:** `/tasks/assets/components/hello_world_mount.js`

```javascript
// Before (Vue 2)
new Vue({...}).$mount('#app')

// After (Vue 3)
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(LiquorTree)
app.mount('#app')
```

### 2.3 Update Router

Same file - convert to Vue Router 4 API:
- `new VueRouter({routes})` -> `createRouter({history: createWebHashHistory(), routes})`

---

## Phase 3: LiquorTree Migration

This is the most complex part. The library has deep Vue 2 patterns that need conversion.

### 3.1 Core Classes

**File:** `/tasks/assets/liquor-tree/src/lib/Tree.js` (727 lines)

- Add `mitt` for event emission (replaces `vm.$emit`)
- Remove Vue instance dependency for events

**File:** `/tasks/assets/liquor-tree/src/lib/Node.js` (695 lines)

- Remove `$set` usage (direct assignment works in Vue 3)

### 3.2 Convert Mixins to Composables

**TreeMixin.js** -> **useTree.js**
- `/tasks/assets/liquor-tree/src/mixins/TreeMixin.js` (220 lines)
- Convert to composable with `ref()`, `computed()`, lifecycle hooks

**DndMixin.js** -> **useDnd.js**
- `/tasks/assets/liquor-tree/src/mixins/DndMixin.js` (250 lines)
- Remove `$set` usage
- Convert to composable

### 3.3 Migrate Tree Components

**NodeContent.js** (render function)
- `/tasks/assets/liquor-tree/src/components/NodeContent.js` (54 lines)
- Update `h()` function usage (import from vue)
- Replace `$scopedSlots` with `useSlots()`
- Change event binding: `on: {click}` -> `onClick`

**TreeNode.vue**
- `/tasks/assets/liquor-tree/src/components/TreeNode.vue` (221 lines)
- Convert to `<script setup>`
- Update `inject` syntax

**DraggableNode.vue**
- `/tasks/assets/liquor-tree/src/components/DraggableNode.vue`
- Convert to Composition API

**TreeRoot.vue** (most complex)
- `/tasks/assets/liquor-tree/src/components/TreeRoot.vue` (325 lines)
- Replace `vue-context` with `@imengyu/vue3-context-menu`
- Convert `provide()` to Composition API
- Fix `v-if` + `v-for` on same element (use computed filter)
- Convert to `<script setup>`

### 3.4 Update Plugin Entry

**File:** `/tasks/assets/liquor-tree/src/main.js`

Update plugin registration for Vue 3:
```javascript
// Before
export default { install(Vue) { Vue.component('tree', TreeRoot) } }

// After
export default { install(app) { app.component('tree', TreeRoot) } }
```

---

## Phase 4: Application Components

### 4.1 Simple Components

**CommitConfirmationModal.vue** (168 lines)
- `/tasks/assets/components/CommitConfirmationModal.vue`
- Convert to `<script setup>`
- Use `defineProps()`, `defineEmits()`

**NodeContent.vue** (app-level)
- `/tasks/assets/components/NodeContent.vue`
- Convert to `<script setup>`, `defineProps()`

**TreeListView.vue** (91 lines)
- `/tasks/assets/components/TreeListView.vue`
- Replace `mapGetters` with Pinia `storeToRefs()`

### 4.2 Main Components

**Journal.vue** (92 lines)
- `/tasks/assets/components/Journal.vue`
- Replace `mapGetters`, `mapActions` with Pinia
- Handle GlobalEvents replacement

**Board.vue** (314 lines) - Main component
- `/tasks/assets/components/Board.vue`
- Replace Vuex helpers with Pinia
- Replace GlobalEvents with `@vueuse/core` useEventListener or manual listeners
- Update slot syntax: `slot-scope` -> `#default`
- Convert to Composition API

---

## Phase 5: Breaking Changes Checklist

| Pattern | Vue 2 | Vue 3 |
|---------|-------|-------|
| Event bus | `vm.$on/$emit` | `mitt` library |
| Scoped slots | `$scopedSlots` | `useSlots()` |
| Render h() | `render(h) {}` | `import { h } from 'vue'` |
| $set | `this.$set(obj, key, val)` | `obj.key = val` |
| Slot syntax | `slot-scope="x"` | `#default="x"` |
| v-if + v-for | Same element | Use computed filter |
| provide/inject | Options API | Composition API |
| Global events | `vue-global-events` | `useEventListener` or manual |
| Context menu | `vue-context` | `@imengyu/vue3-context-menu` |

---

## Files to Modify (Summary)

### Build & Config
- `package.json`
- `rsbuild.config.ts`

### New Files
- `/tasks/assets/stores/boardStore.js`
- `/tasks/assets/liquor-tree/src/composables/useTree.js`
- `/tasks/assets/liquor-tree/src/composables/useDnd.js`

### Entry Point
- `/tasks/assets/components/hello_world_mount.js`

### LiquorTree (8 files)
- `/tasks/assets/liquor-tree/src/main.js`
- `/tasks/assets/liquor-tree/src/lib/Tree.js`
- `/tasks/assets/liquor-tree/src/lib/Node.js`
- `/tasks/assets/liquor-tree/src/components/TreeRoot.vue`
- `/tasks/assets/liquor-tree/src/components/TreeNode.vue`
- `/tasks/assets/liquor-tree/src/components/DraggableNode.vue`
- `/tasks/assets/liquor-tree/src/components/NodeContent.js`
- Delete: `/tasks/assets/liquor-tree/src/mixins/` (replaced by composables)

### Application Components (6 files)
- `/tasks/assets/components/Board.vue`
- `/tasks/assets/components/Journal.vue`
- `/tasks/assets/components/TreeListView.vue`
- `/tasks/assets/components/NodeContent.vue`
- `/tasks/assets/components/CommitConfirmationModal.vue`
- `/tasks/assets/components/hello_world.vue`

### To Delete
- `/tasks/assets/store.js` (replaced by Pinia store)

---

## Execution Order

1. Update `package.json` and install dependencies
2. Update `rsbuild.config.ts`
3. Create Pinia store (`boardStore.js`)
4. Rewrite entry point (`hello_world_mount.js`)
5. Migrate LiquorTree core (`Tree.js`, `Node.js`)
6. Create composables (`useTree.js`, `useDnd.js`)
7. Migrate LiquorTree components (NodeContent.js -> TreeNode -> DraggableNode -> TreeRoot)
8. Update LiquorTree plugin (`main.js`)
9. Migrate simple components (CommitConfirmationModal, NodeContent, TreeListView)
10. Migrate main components (Journal, Board)
11. Test all features: tree operations, drag-and-drop, keyboard navigation, context menus
