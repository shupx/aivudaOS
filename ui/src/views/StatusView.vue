<script setup>
import { useI18n } from 'vue-i18n'
import { useSystemStatus } from '../composables/useSystemStatus'

const { t } = useI18n()
const { user, role, gatewayOnline, totalApps, runningApps, autostartApps, lastSyncAt } = useSystemStatus()
</script>

<template>
  <section class="status-grid">
    <article class="status-card">
      <h2>{{ t('status.title') }}</h2>
      <ul>
        <li>{{ t('status.gateway') }}：<span :class="gatewayOnline ? 'ok' : 'bad'">{{ gatewayOnline ? t('status.online') : t('status.offline') }}</span></li>
        <li>{{ t('status.currentUser') }}：{{ user || '-' }}</li>
        <li>{{ t('status.role') }}：{{ role || '-' }}</li>
        <li>{{ t('status.totalApps') }}：{{ totalApps }}</li>
        <li>{{ t('status.runningApps') }}：{{ runningApps }}</li>
        <li>{{ t('status.autostartApps') }}：{{ autostartApps }}</li>
        <li>{{ t('status.lastSync') }}：{{ lastSyncAt || '-' }}</li>
      </ul>
    </article>
  </section>
</template>
