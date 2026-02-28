<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCard from '../components/apps/AppCard.vue'
import { useAppsPanel } from '../composables/useAppsPanel'

const route = useRoute()
const router = useRouter()

const {
  apps,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
} = useAppsPanel()

const app = computed(() => {
  const appId = String(route.params.appId || '')
  return apps.value.find((item) => item.app_id === appId) || null
})

function backToList() {
  router.push('/dashboard/apps')
}
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>应用详情</h2>
      <div class="panel-actions">
        <button class="btn" @click="backToList">返回列表</button>
        <button class="btn" :disabled="loading" @click="refresh">
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!app && !loading" class="empty-box">
      未找到该应用或应用未安装
    </div>

    <div v-else-if="app" class="apps-grid">
      <AppCard
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        :clickable="false"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>
  </section>
</template>
