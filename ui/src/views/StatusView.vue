<script setup>
import { useSystemStatus } from '../composables/useSystemStatus'

const { user, role, gatewayOnline, totalApps, runningApps, autostartApps, lastSyncAt } = useSystemStatus()
</script>

<template>
  <section class="status-grid">
    <article class="status-card">
      <h2>系统状态</h2>
      <ul>
        <li>网关连通：<span :class="gatewayOnline ? 'ok' : 'bad'">{{ gatewayOnline ? '在线' : '离线' }}</span></li>
        <li>当前用户：{{ user || '-' }}</li>
        <li>角色：{{ role || '-' }}</li>
        <li>应用总数：{{ totalApps }}</li>
        <li>运行中：{{ runningApps }}</li>
        <li>自启动：{{ autostartApps }}</li>
        <li>最近同步：{{ lastSyncAt || '-' }}</li>
      </ul>
    </article>
  </section>
</template>
