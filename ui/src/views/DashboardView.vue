<script setup>
import { RouterView } from 'vue-router'
import { useDashboard } from '../composables/useDashboard'

const {
  sidebarCollapsed,
  isStatusRoute,
  isAppsRoute,
  goStatus,
  goApps,
  toggleSidebar,
  doLogout,
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
          <span v-if="!sidebarCollapsed">系统状态</span>
          <span v-else>S</span>
        </button>

        <button
          class="menu-btn"
          :class="{ active: isAppsRoute }"
          @click="goApps"
        >
          <span v-if="!sidebarCollapsed">应用菜单</span>
          <span v-else>A</span>
        </button>
      </nav>

      <div class="sidebar-bottom" v-if="!sidebarCollapsed">
        <p>{{ user || '-' }} / {{ role || '-' }}</p>
        <button class="btn danger" @click="doLogout">退出登录</button>
      </div>
    </aside>

    <section class="main-panel">
      <div class="main-content">
        <RouterView />
      </div>
    </section>
  </main>
</template>
