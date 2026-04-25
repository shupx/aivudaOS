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
  bulkActionPending,
  searchText,
  compactMode,
  sortOption,
  sortDesc,
  appsSortDropdownVisible,
  setSortOption,
  toggleSortDesc,
  searchResults,
  searchDropdownVisible,
  activeSearchIndex,
  highlightedAppId,
  jumpToAppCard,
  openSearchDropdown,
  handleSearchKeydown,
  refresh,
  toggleCompactMode,
  busyById,
  toggleRunning,
  toggleAutostart,
  restartEnabledApps,
  startEnabledApps,
  stopEveryApp,
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

    <div class="apps-search-row">
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
      <div class="apps-sort-box" style="position: relative;">
        <button
          class="apps-bulk-icon-btn"
          type="button"
          :title="t('apps.sortTooltip')"
          @click="appsSortDropdownVisible = !appsSortDropdownVisible"
        >
            <svg class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="20" y2="6"></line><line x1="8" y1="12" x2="16" y2="12"></line><line x1="10" y1="18" x2="14" y2="18"></line></svg>
        </button>
        <div v-if="appsSortDropdownVisible" class="apps-search-results-dropdown" style="right: 0; left: auto; top: 100%; margin-top: 4px; width: max-content; min-width: 160px;">
          <button
            class="apps-search-result-item"
            @click="setSortOption('name')"
          >
            {{ t('apps.sortByName') }} {{ sortOption === 'name' ? (sortDesc ? '↓' : '↑') : '' }}
          </button>
          <button
            class="apps-search-result-item"
            @click="setSortOption('autostart')"
          >
            {{ t('apps.sortByAutostart') }} {{ sortOption === 'autostart' ? (sortDesc ? '↓' : '↑') : '' }}
          </button>
          <button
            class="apps-search-result-item"
            @click="setSortOption('installed_at')"
          >
            {{ t('apps.sortByInstallationTime') }} {{ sortOption === 'installed_at' ? (sortDesc ? '↓' : '↑') : '' }}
          </button>
        </div>
      </div>
      <button
        class="apps-bulk-icon-btn"
        type="button"
        :title="t('apps.compactToggleTooltip')"
        :aria-label="t('apps.compactToggleTooltip')"
        :aria-pressed="compactMode"
        @click="toggleCompactMode"
      >
        <!-- When in compact mode, show a list icon/larger grid to toggle back. When in normal mode, show a tighter grid icon -->
        <svg v-if="compactMode" class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
        <svg v-else class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
      </button>

      <div class="apps-bulk-actions-row">
        <button
          class="apps-bulk-icon-btn"
          type="button"
          :title="t('apps.restartAutostartTooltip')"
          :aria-label="t('apps.restartAutostartTooltip')"
          :disabled="Boolean(bulkActionPending)"
          @click="restartEnabledApps"
        >
          <svg v-if="bulkActionPending === 'restartAutostart'" class="apps-bulk-icon-symbol animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <svg v-else class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
        </button>
        <button
          class="apps-bulk-icon-btn"
          type="button"
          :title="t('apps.startAutostartTooltip')"
          :aria-label="t('apps.startAutostartTooltip')"
          :disabled="Boolean(bulkActionPending)"
          @click="startEnabledApps"
        >
          <svg v-if="bulkActionPending === 'startAutostart'" class="apps-bulk-icon-symbol animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <svg v-else class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>
        </button>
        <button
          class="apps-bulk-icon-btn apps-bulk-icon-btn-danger"
          type="button"
          :title="t('apps.stopAllTooltip')"
          :aria-label="t('apps.stopAllTooltip')"
          :disabled="Boolean(bulkActionPending)"
          @click="stopEveryApp"
        >
          <svg v-if="bulkActionPending === 'stopAll'" class="apps-bulk-icon-symbol animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <svg v-else class="apps-bulk-icon-symbol" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/></svg>
        </button>
      </div>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!apps.length && !loading" class="empty-box">
      {{ t('apps.noInstalledApps') }}
    </div>

    <div class="apps-grid" :class="{ 'apps-grid-compact': compactMode }">
      <AppCard
        v-for="app in apps"
        :key="app.app_id"
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        :card-id="`app-card-${app.app_id}`"
        :highlighted="highlightedAppId === app.app_id"
        :compact="compactMode"
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
