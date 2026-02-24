<script setup>
import { onMounted } from 'vue'
import { droneState, refreshStatus } from '../services/droneClient'

onMounted(() => {
  if (!droneState.snapshot) {
    refreshStatus()
  }
})
</script>

<template>
  <div class="content-grid">
    <article class="card">
      <h2>会话信息</h2>
      <p>用户：{{ droneState.me?.username }}</p>
      <p>角色：{{ droneState.me?.role }}</p>
      <p>WS 状态：<strong :class="droneState.wsStatus">{{ droneState.wsStatus }}</strong></p>
    </article>

    <article class="card">
      <h2>状态快照</h2>
      <pre>{{ droneState.snapshot }}</pre>
    </article>

    <article class="card">
      <h2>实时状态（WebSocket）</h2>
      <pre>{{ droneState.telemetry }}</pre>
    </article>
  </div>
</template>
