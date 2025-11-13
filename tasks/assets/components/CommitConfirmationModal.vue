<template>
    <div class="modal-backdrop" v-if="show" @click.self="cancel">
        <div class="modal-dialog" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Confirm Commit</h5>
                    <button type="button" class="modal-close" @click="cancel">
                        <span>&times;</span>
                    </button>
                </div>
                <div class="modal-body">
                    <p v-if="itemsToRemove.length > 0">
                        The following items were waiting for 5 periods and will be removed:
                    </p>
                    <ul v-if="itemsToRemove.length > 0" class="items-list">
                        <li v-for="(item, index) in itemsToRemove" :key="index">
                            {{ item.text }}
                        </li>
                    </ul>
                    <p v-else>
                        No items will be removed.
                    </p>
                    <p>Do you want to commit the board?</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" @click="cancel">Cancel</button>
                    <button type="button" class="btn btn-primary" @click="confirm">OK</button>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    props: {
        show: {
            type: Boolean,
            default: false
        },
        itemsToRemove: {
            type: Array,
            default: () => []
        }
    },

    methods: {
        confirm() {
            this.$emit('confirm')
        },

        cancel() {
            this.$emit('cancel')
        }
    }
}
</script>

<style scoped>
.modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1050;
}

.modal-dialog {
    max-width: 500px;
    margin: 1.75rem auto;
}

.modal-content {
    background-color: white;
    border-radius: 0.3rem;
    box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.5);
}

.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    border-bottom: 1px solid #dee2e6;
}

.modal-title {
    margin: 0;
    font-size: 1.25rem;
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
    color: #000;
    opacity: 0.5;
    cursor: pointer;
}

.modal-close:hover {
    opacity: 0.75;
}

.modal-body {
    padding: 1rem;
}

.items-list {
    max-height: 300px;
    overflow-y: auto;
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.items-list li {
    margin-bottom: 0.5rem;
}

.modal-footer {
    display: flex;
    justify-content: flex-end;
    padding: 1rem;
    border-top: 1px solid #dee2e6;
}

.modal-footer button {
    margin-left: 0.5rem;
}

.btn {
    padding: 0.375rem 0.75rem;
    font-size: 1rem;
    border-radius: 0.25rem;
    border: 1px solid transparent;
    cursor: pointer;
}

.btn-secondary {
    color: #fff;
    background-color: #6c757d;
    border-color: #6c757d;
}

.btn-secondary:hover {
    background-color: #5a6268;
    border-color: #545b62;
}

.btn-primary {
    color: #fff;
    background-color: #007bff;
    border-color: #007bff;
}

.btn-primary:hover {
    background-color: #0069d9;
    border-color: #0062cc;
}
</style>
