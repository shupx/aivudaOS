<script setup>
import { RouterView } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDashboard } from '../composables/useDashboard'

const { t } = useI18n()

const {
  sidebarCollapsed,
  isStatusRoute,
  isAppsRoute,
  isConfigRoute,
  isStoreRoute,
  isSystemSettingsRoute,
  locale,
  goStatus,
  goApps,
  goConfigs,
  goStore,
  goSystemSettings,
  toggleSidebar,
  doLogout,
  changeLocale,
  user,
  role,
} = useDashboard()
</script>

<template>
  <main class="dashboard-layout" :class="{ collapsed: sidebarCollapsed }">
    <aside class="left-sidebar">
      <div class="sidebar-top">
        <h1 v-if="!sidebarCollapsed">AivudaOS</h1>
        <button class="icon-btn" @click="toggleSidebar">{{ sidebarCollapsed ? '»' : '«' }}</button>
      </div>

      <nav class="menu-list">
        <button
          class="menu-btn"
          :class="{ active: isStatusRoute }"
          @click="goStatus"
        >
          <span class="menu-btn-content" v-if="!sidebarCollapsed">
            <span class="menu-icon" aria-hidden="true">📊</span>
            <span>{{ t('dashboard.systemStatus') }}</span>
          </span>
          <span class="menu-icon" aria-hidden="true" v-else>📊</span>
        </button>

        <button
          class="menu-btn"
          :class="{ active: isAppsRoute }"
          @click="goApps"
        >
          <span class="menu-btn-content" v-if="!sidebarCollapsed">
            <span class="menu-icon" aria-hidden="true">🧩</span>
            <span>{{ t('dashboard.appsMenu') }}</span>
          </span>
          <span class="menu-icon" aria-hidden="true" v-else>🧩</span>
        </button>

        <button
          class="menu-btn"
          :class="{ active: isConfigRoute }"
          @click="goConfigs"
        >
          <span class="menu-btn-content" v-if="!sidebarCollapsed">
            <span class="menu-icon" aria-hidden="true">⚙️</span>
            <span>{{ t('dashboard.configCenter') }}</span>
          </span>
          <span class="menu-icon" aria-hidden="true" v-else>⚙️</span>
        </button>

        <button
          class="menu-btn"
          :class="{ active: isStoreRoute }"
          @click="goStore"
        >
          <span class="menu-btn-content" v-if="!sidebarCollapsed">
            <span class="menu-icon" aria-hidden="true">🛍️</span>
            <span>{{ t('dashboard.onlineStore') }}</span>
          </span>
          <span class="menu-icon" aria-hidden="true" v-else>🛍️</span>
        </button>

        <button
          class="menu-btn"
          :class="{ active: isSystemSettingsRoute }"
          @click="goSystemSettings"
        >
          <span class="menu-btn-content" v-if="!sidebarCollapsed">
            <span class="menu-icon" aria-hidden="true">🛠️</span>
            <span>{{ t('dashboard.systemSettings') }}</span>
          </span>
          <span class="menu-icon" aria-hidden="true" v-else>🛠️</span>
        </button>
      </nav>

      <div class="sidebar-bottom" v-if="!sidebarCollapsed">
        <label class="muted" for="locale-select">{{ t('dashboard.language') }}</label>
        <select
          id="locale-select"
          class="select-input"
          :value="locale"
          @change="changeLocale($event.target.value)"
        >
          <option value="zh-CN">{{ t('dashboard.languageOptionZh') }}</option>
          <option value="en-US">{{ t('dashboard.languageOptionEn') }}</option>
        </select>
        <p>{{ user || '-' }} / {{ role || '-' }}</p>
        <button class="btn danger" @click="doLogout">{{ t('dashboard.logout') }}</button>
      </div>
    </aside>

    <section class="main-panel">
      <div class="main-content">
        <RouterView />
      </div>
    </section>
  </main>
</template>
