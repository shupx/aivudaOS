<script setup>
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import UploadInstallModal from '../components/apps/UploadInstallModal.vue'
import { useAppsPanel } from '../composables/useAppsPanel'

const { t } = useI18n()

const {
  apps,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadStatus,
  uploadStatusDone,
  uploadOutput,
  uploadFileName,
  uploadHint,
  uploadShowFilePicker,
  openUploadModal,
  closeUploadModal,
  onUploadFileChange,
  submitUpload,
} = useAppsPanel()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <div class="panel-actions panel-title-actions">
        <h2>{{ t('apps.title') }}</h2>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="refresh">
          {{ loading ? t('common.refreshing') : t('common.refresh') }}
        </button>
      </div>
      <div class="panel-actions wrap">
        <button class="link-btn" @click="openUploadModal">{{ t('apps.uploadLink') }}</button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!apps.length && !loading" class="empty-box">
      {{ t('apps.noInstalledApps') }}
    </div>

    <div class="apps-grid">
      <AppCard
        v-for="app in apps"
        :key="app.app_id"
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <UploadInstallModal
      :visible="showUploadModal"
      :busy="uploadBusy"
      :error="uploadError"
      :status="uploadStatus"
      :status-done="uploadStatusDone"
      :output="uploadOutput"
      :file-name="uploadFileName"
      :hint="uploadHint"
      :show-file-picker="uploadShowFilePicker"
      @close="closeUploadModal"
      @file-change="onUploadFileChange"
      @submit="submitUpload"
    />

  </section>
</template>
