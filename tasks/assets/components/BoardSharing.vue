<template>
    <div class="board-sharing">
        <button type="button" class="board-sharing-toggle" @click="toggle">
            {{ sharedWith.length ? `Shared with ${sharedWith.length}` : 'Share' }}
        </button>

        <div v-if="open" class="board-sharing-panel">
            <ul v-if="sharedWith.length" class="board-sharing-users">
                <li v-for="user in sharedWith" :key="user">
                    <span>{{ user }}</span>
                    <button type="button" class="btn-link" @click="change('revoke', user)">Stop sharing</button>
                </li>
            </ul>
            <p v-else class="meta">Only you can see this board.</p>

            <form class="board-sharing-add" @submit.prevent="change('share', username)">
                <input
                    v-model="username"
                    type="text"
                    placeholder="Username"
                    required
                    autocomplete="off"
                    @keyup.stop
                    @keydown.stop
                >
                <button type="submit">Share</button>
            </form>

            <p class="meta">They can see and change this board, tick its unscheduled tasks and commit it.</p>
            <p v-if="error" class="board-sharing-error">{{ error }}</p>
        </div>
    </div>
</template>

<script setup>

import { ref, watch } from 'vue'

import { useBoardStore } from '../store'

const props = defineProps({
    streamId: { type: String, required: true },
})

const boardStore = useBoardStore()

const open = ref(false)
const sharedWith = ref([])
const username = ref('')
const error = ref(null)

function show(response) {
    sharedWith.value = response.shared_with
    error.value = response.error
}

async function load() {
    error.value = null
    try {
        show(await boardStore.loadSharing(props.streamId))
    } catch (e) {
        error.value = e.message
    }
}

function toggle() {
    open.value = !open.value
}

async function change(action, user) {
    if (!user || !user.trim()) {
        return
    }
    try {
        const response = await boardStore.changeSharing(props.streamId, action, user.trim())
        show(response)
        if (action === 'share' && !response.error) {
            username.value = ''
        }
    } catch (e) {
        error.value = e.message
    }
}

// Another board: forget this one's panel and load who it is shared with.
watch(() => props.streamId, () => {
    open.value = false
    username.value = ''
    sharedWith.value = []
    load()
}, { immediate: true })
</script>
