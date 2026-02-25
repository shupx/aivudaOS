<script setup>
import { onMounted } from 'vue'
import { robotState, refreshStatus } from '../services/robotClient'

onMounted(() => {
  if (!robotState.snapshot) {
    refreshStatus()
  }
})
</script>

<template>
  <div class="content-grid">
    <article class="card">
      <h2>会话信息</h2>
      <p>用户：{{ robotState.me?.username }}</p>
      <p>角色：{{ robotState.me?.role }}</p>
      <p>WS 状态：<strong :class="robotState.wsStatus">{{ robotState.wsStatus }}</strong></p>
    </article>

    <article class="card">
      <h2>状态快照</h2>
      <pre>{{ robotState.snapshot }}</pre>
    </article>

    <article class="card">
      <h2>实时状态（WebSocket）</h2>
      <pre>{{ robotState.telemetry }}</pre>
    </article>
  </div>
</template>
