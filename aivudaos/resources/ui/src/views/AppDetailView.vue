<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import { useDomAppendLog } from '../composables/useDomAppendLog'
import { useAppDetailPage } from '../composables/useAppDetailPage'
import { NCard, NSpace, NButton, NText, NGrid, NGi, NSelect, NCheckbox, NLog, NModal, NInput, NIcon, NAlert } from 'naive-ui'
import { ArrowLeft, RefreshCw, Download, FileUp, Settings, Trash2, PowerOff, MonitorPlay, Send } from 'lucide-vue-next'

const { t } = useI18n()

const {
  app,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
  logText,
  logBusy,
  logError,
  loadLogs,
  clearAndReloadLogs,
  actionBusy,
  actionError,
  actionMessage,
  actionLiveStatus,
  actionLiveStatusDone,
  actionLiveOutput,
  showActionOutputModal,
  actionCancelBusy,
  closeActionOutputModal,
  cancelCurrentAction,
  actionInteractiveInput,
  actionInteractiveReady,
  actionInteractiveMaskInput,
  setActionInteractiveInput,
  setActionInteractiveMaskInput,
  submitActionInteractiveInput,
  versions,
  selectedVersion,
  switchWithRestart,
  canSwitchVersion,
  goToManualUpload,
  goToConfigPage,
  runUpdateThisVersionScript,
  uninstallVersionOnly,
  uninstallPurge,
  canUninstall,
  runUninstall,
  runSwitchVersion,
  backToList,
} = useAppDetailPage()

const appLogPlaceholder = computed(() => t('appDetail.noLogOutput'))
const actionLogPlaceholder = computed(() => t('appDetail.waitingOutput'))

const {
  logRef: appLogRef,
  onLogScroll: onAppLogScroll,
} = useDomAppendLog(logText, { placeholderRef: appLogPlaceholder })

const {
  logRef: actionLogRef,
  onLogScroll: onActionLogScroll,
} = useDomAppendLog(actionLiveOutput, {
  visibleRef: showActionOutputModal,
  placeholderRef: actionLogPlaceholder,
})
</script>

<template>
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <NSpace align="center">
        <NButton quaternary circle @click="backToList" :title="t('appDetail.backToList')">
           <template #icon><NIcon><ArrowLeft /></NIcon></template>
        </NButton>
        <NText style="font-size: 20px; font-weight: 600;">{{ t('appDetail.title') }}</NText>
      </NSpace>
      <NButton secondary size="small" :loading="loading" @click="refresh">
        <template #icon><NIcon><RefreshCw /></NIcon></template>
        {{ t('common.refresh') }}
      </NButton>
    </div>

    <NAlert v-if="error" type="error" style="margin-bottom: 24px;">{{ error }}</NAlert>

    <NCard v-if="!app && !loading" style="margin-bottom: 24px;">
      <NText depth="3">{{ t('appDetail.notFound') }}</NText>
    </NCard>

    <div v-else-if="app" style="margin-bottom: 24px;">
      <AppCard
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        :clickable="false"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <NCard v-if="app" :title="t('appDetail.logTitle')" style="margin-bottom: 24px;">
      <template #header-extra>
        <NSpace>
          <NButton size="small" :loading="logBusy" @click="loadLogs">
            <template #icon><NIcon><Download /></NIcon></template>
            {{ t('appDetail.pullLatest') }}
          </NButton>
          <NButton size="small" @click="clearAndReloadLogs">
            <template #icon><NIcon><RefreshCw /></NIcon></template>
            {{ t('appDetail.clearAndReload') }}
          </NButton>
        </NSpace>
      </template>

      <NAlert v-if="logError" type="error" style="margin-bottom: 12px;">{{ logError }}</NAlert>
      <NLog :log="logText" :rows="16" trim style="border: 1px solid #334155; border-radius: 12px; background-color: #0f172a; --n-text-color: #e2e8f0; color: #e2e8f0;" @scroll="onAppLogScroll" />
    </NCard>

    <NCard v-if="app" :title="t('appDetail.actionsTitle')" style="margin-bottom: 24px;">
      <NAlert v-if="actionError" type="error" style="margin-bottom: 16px;">{{ actionError }}</NAlert>
      <NAlert v-if="actionMessage" type="success" style="margin-bottom: 16px;">{{ actionMessage }}</NAlert>
      <NAlert v-if="actionLiveStatus" :type="actionLiveStatusDone ? 'success' : 'info'" style="margin-bottom: 16px;">
        {{ t('appDetail.statusPrefix', { status: actionLiveStatus }) }}
      </NAlert>

      <NGrid x-gap="16" y-gap="16" cols="1 m:2" responsive="screen">
        <NGi>
          <NCard size="small" bordered>
            <template #header>
              <NText style="font-size: 15px; font-weight: 600;">{{ t('appDetail.manualUploadVersion') }}</NText>
            </template>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              <NText depth="3">{{ t('appDetail.manualUploadHint') }}</NText>
              <NButton size="small" @click="goToManualUpload" style="align-self: flex-start;">
                <template #icon><NIcon><FileUp /></NIcon></template>
                {{ t('appDetail.goManualUpload') }}
              </NButton>
            </div>
          </NCard>
        </NGi>

        <NGi>
          <NCard size="small" bordered>
            <template #header>
              <NText style="font-size: 15px; font-weight: 600;">{{ t('appDetail.configTitle') }}</NText>
            </template>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              <NText depth="3">{{ t('appDetail.configHint') }}</NText>
              <NButton size="small" @click="goToConfigPage" style="align-self: flex-start;">
                <template #icon><NIcon><Settings /></NIcon></template>
                {{ t('appDetail.goConfigPage') }}
              </NButton>
            </div>
          </NCard>
        </NGi>

        <NGi>
          <NCard size="small" bordered>
            <template #header>
              <NText style="font-size: 15px; font-weight: 600;">{{ t('appDetail.manageVersions') }}</NText>
            </template>
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <NSelect
                  v-model:value="selectedVersion"
                  size="small"
                  style="width: 160px;"
                  :options="versions.map(v => ({ label: v, value: v }))"
                />
                <NCheckbox v-model:checked="switchWithRestart">{{ t('appDetail.restartAfterSwitch') }}</NCheckbox>
              </div>
              <NSpace>
                <NButton size="small" :disabled="!canSwitchVersion || actionBusy" :loading="actionBusy" @click="runSwitchVersion">
                  <template #icon><NIcon><MonitorPlay /></NIcon></template>
                  {{ t('appDetail.switchVersion') }}
                </NButton>
                <NButton size="small" :disabled="!selectedVersion || actionBusy" :loading="actionBusy" @click="runUpdateThisVersionScript">
                  <template #icon><NIcon><RefreshCw /></NIcon></template>
                  {{ t('appDetail.updateThisVersion') }}
                </NButton>
              </NSpace>
            </div>
          </NCard>
        </NGi>

        <NGi>
          <NCard size="small" bordered>
            <template #header>
              <NText style="font-size: 15px; font-weight: 600;">{{ t('appDetail.uninstallTitle') }}</NText>
            </template>
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <NSpace>
                <NCheckbox v-model:checked="uninstallVersionOnly">{{ t('appDetail.uninstallCurrentOnly') }}</NCheckbox>
                <NCheckbox v-model:checked="uninstallPurge">{{ t('appDetail.purgeConfig') }}</NCheckbox>
              </NSpace>
              <NButton size="small" type="error" :disabled="!canUninstall" :loading="actionBusy" @click="runUninstall" style="align-self: flex-start;">
                <template #icon><NIcon><Trash2 /></NIcon></template>
                {{ t('appDetail.executeUninstall') }}
              </NButton>
            </div>
          </NCard>
        </NGi>
      </NGrid>
    </NCard>

    <NModal :show="showActionOutputModal" :mask-closable="!actionBusy" @mask-click="actionBusy ? null : closeActionOutputModal()">
      <NCard
        style="width: min(700px, 95vw);"
        :title="t('appDetail.actionOutputTitle')"
        :bordered="false"
        size="huge"
        role="dialog"
        aria-modal="true"
      >
        <div style="display: flex; flex-direction: column; gap: 16px;">
          <NText v-if="actionLiveStatus" :type="actionLiveStatusDone ? 'success' : 'default'">
            {{ t('appDetail.statusPrefix', { status: actionLiveStatus }) }}
          </NText>
          <NAlert v-if="actionError" type="error">{{ actionError }}</NAlert>

          <div style="display: flex; flex-direction: column; gap: 8px;">
            <NText>{{ t('apps.interactiveInputLabel') }}</NText>
            <div style="display: flex; gap: 8px;">
              <NInput
                :type="actionInteractiveMaskInput ? 'password' : 'text'"
                :placeholder="t('apps.interactiveInputPlaceholder')"
                :value="actionInteractiveInput"
                @update:value="(val) => setActionInteractiveInput(val)"
                @keydown.enter.prevent="submitActionInteractiveInput"
                style="flex: 1;"
              />
              <NButton @click="setActionInteractiveMaskInput(!actionInteractiveMaskInput)">
                {{ actionInteractiveMaskInput ? t('apps.interactiveShowInput') : t('apps.interactiveHideInput') }}
              </NButton>
              <NButton type="primary" :disabled="!actionInteractiveInput || !actionInteractiveReady" @click="submitActionInteractiveInput">
                <template #icon><NIcon><Send /></NIcon></template>
                {{ t('apps.interactiveSend') }}
              </NButton>
            </div>
          </div>

          <NLog
            :log="actionLiveOutput"
            :rows="14"
            trim
            style="border: 1px solid #334155; border-radius: 12px; background-color: #0f172a; --n-text-color: #e2e8f0; color: #e2e8f0;"
          />

          <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px;">
            <NButton :disabled="actionBusy" @click="closeActionOutputModal">{{ t('common.close') }}</NButton>
            <NButton v-if="actionBusy" type="error" :loading="actionCancelBusy" @click="cancelCurrentAction">
              <template #icon><NIcon><PowerOff /></NIcon></template>
              {{ t('apps.exitInstall') }}
            </NButton>
          </div>
        </div>
      </NCard>
    </NModal>
  </section>
</template>
