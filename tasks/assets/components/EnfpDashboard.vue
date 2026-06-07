<template>
    <div class="enfp-dashboard">
        <h1 class="mb-4 text-center">Cognitive Functions</h1>

        <p v-if="loading" class="text-center">Loading…</p>

        <template v-else>
            <!-- The four functions arranged in a 2x2 square with a circle on the
                 center crosshair. Counts sit in the four quadrants near the
                 middle; labels sit outside, two on top and two on the bottom. -->
            <div class="enfp-square-wrap">
                <svg
                    class="enfp-square"
                    viewBox="0 0 400 440"
                    role="img"
                    aria-label="Cognitive function counts"
                >
                    <!-- outer square -->
                    <rect
                        x="40" y="60" width="320" height="320"
                        class="enfp-square-outline"
                    />
                    <!-- dividing lines through the centre (the crosshair) -->
                    <line x1="200" y1="60" x2="200" y2="380" class="enfp-grid-line" />
                    <line x1="40" y1="220" x2="360" y2="220" class="enfp-grid-line" />

                    <!-- circle centred exactly on the crosshair -->
                    <circle cx="200" cy="220" r="120" class="enfp-circle" />

                    <!-- counts: one per quadrant, clustered near the centre -->
                    <text x="160" y="190" class="enfp-count">{{ displayCounts.ne }}</text>
                    <text x="240" y="190" class="enfp-count">{{ displayCounts.fi }}</text>
                    <text x="160" y="262" class="enfp-count">{{ displayCounts.te }}</text>
                    <text x="240" y="262" class="enfp-count">{{ displayCounts.si }}</text>

                    <!-- labels around the square: two on top, two on the bottom -->
                    <text x="120" y="36" class="enfp-label">
                        <tspan class="enfp-label-code">Ne</tspan>
                    </text>
                    <text x="120" y="52" class="enfp-label enfp-label-name">Extraverted Intuition</text>

                    <text x="280" y="36" class="enfp-label">
                        <tspan class="enfp-label-code">Fi</tspan>
                    </text>
                    <text x="280" y="52" class="enfp-label enfp-label-name">Introverted Feeling</text>

                    <text x="120" y="410" class="enfp-label">
                        <tspan class="enfp-label-code">Te</tspan>
                    </text>
                    <text x="120" y="426" class="enfp-label enfp-label-name">Extraverted Thinking</text>

                    <text x="280" y="410" class="enfp-label">
                        <tspan class="enfp-label-code">Si</tspan>
                    </text>
                    <text x="280" y="426" class="enfp-label enfp-label-name">Introverted Sensing</text>
                </svg>
            </div>

            <p v-if="!usingChallengeTally" class="text-muted text-center small mb-4">
                Showing lifetime totals.
            </p>

            <!-- Progress toward the CLOSEST reward only. -->
            <section class="card mb-4">
                <div class="card-body">
                    <template v-if="primaryChallenge && nextStage">
                        <h3 class="h5 mb-1">Next reward</h3>
                        <p class="text-muted small mb-3">{{ primaryChallenge.name }}</p>

                        <div class="d-flex align-items-center mb-3">
                            <span v-if="nextStage.reward_emoji" class="enfp-reward-emoji mr-2">
                                {{ nextStage.reward_emoji }}
                            </span>
                            <span class="h5 mb-0">{{ nextStage.reward_name }}</span>
                            <span v-if="nextStage.is_completion" class="ml-2" title="completes the challenge">🏁</span>
                        </div>

                        <div class="mb-2">
                            <div class="d-flex justify-content-between small text-muted">
                                <span>Overall progress</span>
                                <span>{{ overallProgress.current }} / {{ overallProgress.target }}</span>
                            </div>
                            <div class="progress" style="height: 1.5rem;">
                                <div
                                    class="progress-bar"
                                    role="progressbar"
                                    :style="{ width: overallProgress.percent + '%' }"
                                    :aria-valuenow="overallProgress.current"
                                    aria-valuemin="0"
                                    :aria-valuemax="overallProgress.target"
                                >
                                    {{ overallProgress.percent }}%
                                </div>
                            </div>
                        </div>

                        <!-- per-function progress toward the next stage's target -->
                        <div class="row mt-3">
                            <div class="col-6 col-md-3 mb-2" v-for="fn in functions" :key="fn.key">
                                <div class="small text-muted">
                                    {{ fn.code }}: {{ currentTally[fn.key] || 0 }} / {{ nextStage.target[fn.key] }}
                                </div>
                                <div class="progress" style="height: 0.5rem;">
                                    <div
                                        class="progress-bar"
                                        role="progressbar"
                                        :style="{ width: progressPercent(fn.key) + '%' }"
                                        :aria-valuenow="currentTally[fn.key] || 0"
                                        aria-valuemin="0"
                                        :aria-valuemax="nextStage.target[fn.key]"
                                    ></div>
                                </div>
                            </div>
                        </div>
                    </template>

                    <p v-else-if="primaryChallenge" class="mb-0 text-success">
                        🎉 All rewards in “{{ primaryChallenge.name }}” have been claimed.
                    </p>

                    <p v-else class="mb-0 text-muted">
                        No active challenges. Create one in the admin to start earning rewards.
                    </p>
                </div>
            </section>

            <section class="card">
                <div class="card-body">
                    <h3 class="h5">Log an element</h3>
                    <form @submit.prevent="logElement">
                        <div class="form-group">
                            <label for="enfp-function">Function</label>
                            <select id="enfp-function" v-model="form.function" class="form-control" required>
                                <option v-for="fn in functions" :key="fn.code" :value="fn.code">
                                    {{ fn.code }} — {{ fn.label }}
                                </option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="enfp-description">What did you do?</label>
                            <textarea
                                id="enfp-description"
                                v-model="form.description"
                                class="form-control"
                                rows="2"
                            ></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary" :disabled="saving">
                            {{ saving ? 'Logging…' : 'Log' }}
                        </button>
                    </form>
                </div>
            </section>
        </template>
    </div>
</template>

<script>
// CSRF-aware fetch helper (same pattern as store.js / hello_world_mount.js).
const apiRequest = async (url, options = {}) => {
    const token = document.body.querySelector('[name=csrfmiddlewaretoken]');
    const defaultHeaders = {
        'X-CSRFToken': token ? token.value : '',
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(url, {
        ...options,
        headers: defaultHeaders
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
};

export default {
    data() {
        return {
            loading: true,
            saving: false,
            totals: { ne: 0, fi: 0, te: 0, si: 0 },
            challenges: [],
            functions: [
                { code: 'Ne', key: 'ne', label: 'Extraverted Intuition' },
                { code: 'Fi', key: 'fi', label: 'Introverted Feeling' },
                { code: 'Te', key: 'te', label: 'Extraverted Thinking' },
                { code: 'Si', key: 'si', label: 'Introverted Sensing' },
            ],
            form: { function: 'Ne', description: '' },
        };
    },

    computed: {
        // Progress tracks the first active challenge.
        primaryChallenge() {
            return this.challenges.length ? this.challenges[0] : null;
        },
        usingChallengeTally() {
            return !!this.primaryChallenge;
        },
        currentTally() {
            return this.primaryChallenge ? this.primaryChallenge.current : this.totals;
        },
        nextStage() {
            return this.primaryChallenge ? this.primaryChallenge.next_stage : null;
        },
        // Counts shown inside the circle: the active challenge's tally if a
        // challenge is running, otherwise lifetime totals.
        displayCounts() {
            return this.usingChallengeTally ? this.currentTally : this.totals;
        },
        // Overall progress toward the next stage: sum across the four functions.
        overallProgress() {
            if (!this.nextStage) {
                return { current: 0, target: 0, percent: 0 };
            }
            let current = 0;
            let target = 0;
            for (const fn of this.functions) {
                const t = this.nextStage.target[fn.key] || 0;
                target += t;
                // cap each function's contribution at its target so an
                // over-achieved function doesn't inflate the overall bar
                current += Math.min(this.currentTally[fn.key] || 0, t);
            }
            const percent = target ? Math.min(100, Math.round((current / target) * 100)) : 100;
            return { current, target, percent };
        },
    },

    methods: {
        async load() {
            const data = await apiRequest('/enfp/summary/');
            this.totals = data.totals;
            this.challenges = data.challenges;
            this.loading = false;
        },

        progressPercent(key) {
            if (!this.nextStage) return 0;
            const target = this.nextStage.target[key];
            if (!target) return 100;
            const current = this.currentTally[key] || 0;
            return Math.min(100, Math.round((current / target) * 100));
        },

        async logElement() {
            this.saving = true;
            try {
                await apiRequest('/enfp/api/elements/', {
                    method: 'POST',
                    body: JSON.stringify({
                        function: this.form.function,
                        description: this.form.description,
                    }),
                });
                this.form.description = '';
                await this.load();
            } finally {
                this.saving = false;
            }
        },
    },

    mounted() {
        this.load();
    },
};
</script>

<!-- Styles live in tasks/assets/styles/_enfp.scss (imported via app.scss). -->

