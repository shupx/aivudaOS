<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { bootstrapSession, droneState, logout } from './services/droneClient'

const router = useRouter()
const isLoggedIn = computed(() => Boolean(droneState.token))

onMounted(() => {
  bootstrapSession()
})

function doLogout() {
  logout()
  router.replace('/login')
}
</script>

<template>
  <main class="layout">
    <aside v-if="isLoggedIn" class="sidebar">
      <h1>Drone Console</h1>
      <nav class="nav-list">
        <RouterLink to="/status" class="nav-item">实时状态</RouterLink>
        <RouterLink to="/config" class="nav-item">配置管理</RouterLink>
      </nav>
      <div class="sidebar-footer">
        <p class="tip">{{ droneState.me?.username || 'admin' }}</p>
        <button class="btn danger" @click="doLogout">退出</button>
      </div>
    </aside>

    <section class="content" :class="{ full: !isLoggedIn }">
      <RouterView />
    </section>
  </main>
</template>
