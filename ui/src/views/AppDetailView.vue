<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import { useDomAppendLog } from '../composables/useDomAppendLog'
import { useAppDetailPage } from '../composables/useAppDetailPage'

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
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('appDetail.title') }}</h2>
      <div class="panel-actions">
        <button class="btn" @click="backToList">{{ t('appDetail.backToList') }}</button>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="refresh">
          {{ loading ? t('common.loadingShort') : t('common.refresh') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!app && !loading" class="empty-box">
      {{ t('appDetail.notFound') }}
    </div>

    <div v-else-if="app" class="apps-grid">
      <AppCard
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        :clickable="false"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <article v-if="app" class="log-panel">
      <header class="log-header">
        <h3>{{ t('appDetail.logTitle') }}</h3>
        <div class="panel-actions">
          <button class="btn btn-stable-log" :disabled="logBusy" @click="loadLogs">
            {{ logBusy ? t('appDetail.loadingLogs') : t('appDetail.pullLatest') }}
          </button>
          <button class="btn" @click="clearAndReloadLogs">{{ t('appDetail.clearAndReload') }}</button>
        </div>
      </header>

      <p v-if="logError" class="error-text">{{ logError }}</p>
      <pre ref="appLogRef" class="log-output" @scroll="onAppLogScroll"></pre>
    </article>

    <article v-if="app" class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appDetail.actionsTitle') }}</h3>
      </header>

      <p v-if="actionError" class="error-text">{{ actionError }}</p>
      <p v-if="actionMessage" class="ok-text">{{ actionMessage }}</p>
      <p
        v-if="actionLiveStatus"
        :class="actionLiveStatusDone ? 'ok-text' : 'muted'"
      >
        {{ t('appDetail.statusPrefix', { status: actionLiveStatus }) }}
      </p>

      <div class="actions-grid">
        <div class="action-block">
          <h4>{{ t('appDetail.manualUploadVersion') }}</h4>
          <div class="panel-actions wrap">
            <button class="btn" @click="goToManualUpload">
              {{ t('appDetail.goManualUpload') }}
            </button>
          </div>
          <p class="muted">{{ t('appDetail.manualUploadHint') }}</p>
        </div>

        <div class="action-block">
          <h4>{{ t('appDetail.configTitle') }}</h4>
          <div class="panel-actions wrap">
            <button class="btn" @click="goToConfigPage">
              {{ t('appDetail.goConfigPage') }}
            </button>
          </div>
          <p class="muted">{{ t('appDetail.configHint') }}</p>
        </div>

        <div class="action-block">
          <h4>{{ t('appDetail.manageVersions') }}</h4>
          <div class="panel-actions wrap">
            <select v-model="selectedVersion" class="select-input">
              <option v-for="version in versions" :key="version" :value="version">
                {{ version }}
              </option>
            </select>
            <label class="check-item">
              <input v-model="switchWithRestart" type="checkbox">
              {{ t('appDetail.restartAfterSwitch') }}
            </label>
            <button class="btn" :disabled="!canSwitchVersion || actionBusy" @click="runSwitchVersion">
              {{ actionBusy ? t('common.processing') : t('appDetail.switchVersion') }}
            </button>
            <button class="btn" :disabled="!selectedVersion || actionBusy" @click="runUpdateThisVersionScript">
              {{ actionBusy ? t('common.processing') : t('appDetail.updateThisVersion') }}
            </button>
          </div>
        </div>

        <div class="action-block action-block-wide">
          <h4>{{ t('appDetail.uninstallTitle') }}</h4>
          <div class="panel-actions wrap">
            <label class="check-item">
              <input v-model="uninstallVersionOnly" type="checkbox">
              {{ t('appDetail.uninstallCurrentOnly') }}
            </label>
            <label class="check-item">
              <input v-model="uninstallPurge" type="checkbox">
              {{ t('appDetail.purgeConfig') }}
            </label>
            <button class="btn danger" :disabled="!canUninstall" @click="runUninstall">
              {{ actionBusy ? t('common.processing') : t('appDetail.executeUninstall') }}
            </button>
          </div>
        </div>
      </div>
    </article>

    <div v-if="showActionOutputModal" class="modal-overlay" @click.self="actionBusy ? null : closeActionOutputModal">
      <section class="modal-card modal-wide">
        <header class="modal-header">
          <h3>{{ t('appDetail.actionOutputTitle') }}</h3>
        </header>

        <p
          v-if="actionLiveStatus"
          :class="actionLiveStatusDone ? 'ok-text' : 'muted'"
        >
          {{ t('appDetail.statusPrefix', { status: actionLiveStatus }) }}
        </p>
        <p v-if="actionError" class="error-text">{{ actionError }}</p>

        <div class="field">
          <label>{{ t('apps.interactiveInputLabel') }}</label>
          <div class="panel-actions">
            <input
              class="input"
              :type="actionInteractiveMaskInput ? 'password' : 'text'"
              autocomplete="off"
              :placeholder="t('apps.interactiveInputPlaceholder')"
              :value="actionInteractiveInput"
              @input="setActionInteractiveInput($event?.target?.value || '')"
              @keydown.enter.prevent="submitActionInteractiveInput"
            >
            <button
              class="btn"
              type="button"
              @click="setActionInteractiveMaskInput(!actionInteractiveMaskInput)"
            >
              {{ actionInteractiveMaskInput ? t('apps.interactiveShowInput') : t('apps.interactiveHideInput') }}
            </button>
            <button
              class="btn"
              :disabled="!actionInteractiveInput || !actionInteractiveReady"
              @click="submitActionInteractiveInput"
            >
              {{ t('apps.interactiveSend') }}
            </button>
          </div>
        </div>

        <pre ref="actionLogRef" class="log-output" @scroll="onActionLogScroll"></pre>

        <footer class="panel-actions">
          <button class="btn" :disabled="actionBusy" @click="closeActionOutputModal">{{ t('common.close') }}</button>
          <button v-if="actionBusy" class="btn danger" @click="cancelCurrentAction">
            {{ actionCancelBusy ? t('common.processing') : t('apps.exitInstall') }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
