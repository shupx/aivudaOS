<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import SwitchToggle from './SwitchToggle.vue'

const props = defineProps({
  app: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  clickable: { type: Boolean, default: true },
})

const emit = defineEmits(['toggle-running', 'toggle-autostart'])
const router = useRouter()

const description = computed(() => props.app.description || '无描述')

function onRunningChange(nextValue) {
  emit('toggle-running', props.app, nextValue)
}

function onAutostartChange(nextValue) {
  emit('toggle-autostart', props.app, nextValue)
}

function goDetail() {
  if (!props.clickable) return
  router.push(`/dashboard/apps/${encodeURIComponent(props.app.app_id)}`)
}
</script>

<template>
  <article
    class="app-card"
    :class="{ 'card-clickable': clickable }"
    :tabindex="clickable ? 0 : -1"
    @click="goDetail"
    @keydown.enter.prevent="goDetail"
    @keydown.space.prevent="goDetail"
  >
    <header class="app-card-header">
      <h3>{{ app.name || app.app_id }}</h3>
      <span class="app-version">v{{ app.active_version || '-' }}</span>
    </header>

    <div class="app-meta">
      <p><strong>app_id:</strong> {{ app.app_id }}</p>
      <p><strong>描述:</strong> {{ description }}</p>
      <p><strong>状态:</strong> {{ app.running ? '运行中' : '已停止' }}</p>
    </div>

    <div class="switch-row">
      <div class="switch-item" @click.stop>
        <span>启动</span>
        <SwitchToggle :model-value="Boolean(app.running)" :disabled="busy" @update:model-value="onRunningChange" />
      </div>

      <div class="switch-item" @click.stop>
        <span>自启动</span>
        <SwitchToggle :model-value="Boolean(app.autostart)" :disabled="busy" @update:model-value="onAutostartChange" />
      </div>
    </div>
  </article>
</template>
