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
  searchText,
  searchResults,
  searchDropdownVisible,
  activeSearchIndex,
  highlightedAppId,
  jumpToAppCard,
  openSearchDropdown,
  handleSearchKeydown,
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
  uploadInteractiveInput,
  uploadInteractiveReady,
  uploadInteractiveMaskInput,
  uploadCancelBusy,
  openUploadModal,
  closeUploadModal,
  setInteractiveInput,
  setInteractiveMaskInput,
  onUploadFileChange,
  submitUpload,
  cancelCurrentUpload,
  submitInteractiveInput,
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

    <div class="apps-search-box">
      <div class="search-input-shell">
        <input
          id="apps-search-input"
          v-model="searchText"
          class="select-input apps-search-input"
          type="text"
          :placeholder="t('apps.searchPlaceholder')"
          @focus="openSearchDropdown"
          @keydown="handleSearchKeydown"
        >
        <button v-if="searchText" class="search-clear-btn" @click="searchText = ''">x</button>
      </div>
      <div v-if="searchDropdownVisible" class="apps-search-results-dropdown">
        <button
          v-for="(app, index) in searchResults"
          :key="`search-${app.app_id}`"
          class="apps-search-result-item"
          :class="{ 'apps-search-result-item-active': index === activeSearchIndex }"
          @click="jumpToAppCard(app)"
        >
          {{ app.name || app.app_id }}
        </button>
        <div v-if="!searchResults.length" class="apps-search-result-empty">
          {{ t('apps.searchEmpty') }}
        </div>
      </div>
    </div>

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
        :card-id="`app-card-${app.app_id}`"
        :highlighted="highlightedAppId === app.app_id"
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
      :cancel-busy="uploadCancelBusy"
      :interactive-input="uploadInteractiveInput"
      :interactive-ready="uploadInteractiveReady"
      :interactive-mask-input="uploadInteractiveMaskInput"
      @close="closeUploadModal"
      @file-change="onUploadFileChange"
      @submit="submitUpload"
      @cancel-operation="cancelCurrentUpload"
      @interactive-input="setInteractiveInput"
      @interactive-mask-change="setInteractiveMaskInput"
      @interactive-submit="submitInteractiveInput"
    />

  </section>
</template>
