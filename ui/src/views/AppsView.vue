<script setup>
import AppCard from '../components/apps/AppCard.vue'
import { useAppsPanel } from '../composables/useAppsPanel'

const {
  apps,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
} = useAppsPanel()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>应用菜单</h2>
      <button class="btn" :disabled="loading" @click="refresh">
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!apps.length && !loading" class="empty-box">
      当前没有已安装应用
    </div>

    <div class="apps-grid">
      <AppCard
        v-for="app in apps"
        :key="app.app_id"
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>
  </section>
</template>
