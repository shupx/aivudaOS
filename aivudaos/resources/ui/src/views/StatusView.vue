<script setup>
import { useI18n } from 'vue-i18n'
import { useSystemStatus } from '../composables/useSystemStatus'
import { NCard, NGrid, NGi, NStatistic, NTag, NDescriptions, NDescriptionsItem, NText } from 'naive-ui'
import { Activity, Blocks, PlayCircle, Clock } from 'lucide-vue-next'

const { t } = useI18n()
const { user, role, aivudaosVersion, gatewayOnline, totalApps, runningApps, autostartApps, lastSyncAt } = useSystemStatus()
</script>

<template>
  <section>
    <div style="margin-bottom: 24px;">
       <NText style="font-size: 20px; font-weight: 600;">{{ t('status.title') }}</NText>
    </div>

    <NGrid x-gap="16" y-gap="16" cols="1 s:2 m:4" responsive="screen">
      <NGi>
        <NCard>
          <NStatistic :label="t('status.gateway')">
            <template #prefix>
              <Activity style="margin-right: 8px;" :color="gatewayOnline ? '#10b981' : '#ef4444'" />
            </template>
            <NTag :type="gatewayOnline ? 'success' : 'error'">
              {{ gatewayOnline ? t('status.online') : t('status.offline') }}
            </NTag>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi>
        <NCard>
          <NStatistic :label="t('status.totalApps')" :value="totalApps">
             <template #prefix>
                <Blocks style="margin-right: 8px; color: #64748b;" />
             </template>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi>
        <NCard>
          <NStatistic :label="t('status.runningApps')" :value="runningApps">
             <template #prefix>
                <PlayCircle style="margin-right: 8px; color: #3b82f6;" />
             </template>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi>
        <NCard>
          <NStatistic :label="t('status.autostartApps')" :value="autostartApps">
             <template #prefix>
                <Clock style="margin-right: 8px; color: #f59e0b;" />
             </template>
          </NStatistic>
        </NCard>
      </NGi>
    </NGrid>

    <NCard :title="t('status.detailsTitle')" style="margin-top: 16px;">
      <NDescriptions bordered column="1 s:2" responsive="screen">
        <NDescriptionsItem :label="t('status.aivudaosVersion')">{{ aivudaosVersion || '-' }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('status.currentUser')">{{ user || '-' }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('status.role')">{{ role || '-' }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('status.lastSync')">{{ lastSyncAt || '-' }}</NDescriptionsItem>
      </NDescriptions>
    </NCard>
  </section>
</template>
