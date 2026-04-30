<script setup>
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import UploadInstallModal from '../components/apps/UploadInstallModal.vue'
import { useAppsPanel } from '../composables/useAppsPanel'
import {
  NSpace,
  NButton,
  NInput,
  NIcon,
  NDropdown,
  NAlert,
  NEmpty,
  NText,
  NGrid,
  NGi
} from 'naive-ui'
import {
  Upload,
  RefreshCw,
  Search,
  X,
  ArrowUpDown,
  LayoutGrid,
  List,
  RotateCcw,
  Play,
  Square
} from 'lucide-vue-next'

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

const sortOptions = [
  { label: t('apps.sortByName') + (sortOption.value === 'name' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'name' },
  { label: t('apps.sortByAutostart') + (sortOption.value === 'autostart' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'autostart' },
  { label: t('apps.sortByInstallationTime') + (sortOption.value === 'installed_at' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'installed_at' }
]

const handleSortSelect = (key) => {
  setSortOption(key)
}
</script>

<template>
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <NSpace align="center">
        <NText style="font-size: 20px; font-weight: 600;">{{ t('apps.title') }}</NText>
        <NButton secondary size="small" :loading="loading" @click="refresh">
          <template #icon><NIcon><RefreshCw /></NIcon></template>
          {{ t('common.refresh') }}
        </NButton>
      </NSpace>
      <NButton type="primary" size="small" @click="openUploadModal">
        <template #icon><NIcon><Upload /></NIcon></template>
        {{ t('apps.uploadLink') }}
      </NButton>
    </div>

    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap;">
      <div style="position: relative; width: 320px; max-width: 100%;">
        <NInput
          v-model:value="searchText"
          :placeholder="t('apps.searchPlaceholder')"
          clearable
          @focus="openSearchDropdown"
          @keydown="handleSearchKeydown"
        >
          <template #prefix>
            <NIcon><Search /></NIcon>
          </template>
        </NInput>
        <!-- Custom Dropdown for Search Results -->
        <div v-if="searchDropdownVisible && searchResults.length > 0" class="apps-search-results-dropdown">
          <button
            v-for="(app, index) in searchResults"
            :key="`search-${app.app_id}`"
            class="apps-search-result-item"
            :class="{ 'apps-search-result-item-active': index === activeSearchIndex }"
            @click="jumpToAppCard(app)"
          >
            {{ app.name || app.app_id }}
          </button>
        </div>
      </div>

      <NDropdown trigger="click" :options="sortOptions" @select="handleSortSelect">
        <NButton quaternary circle>
          <template #icon><NIcon><ArrowUpDown /></NIcon></template>
        </NButton>
      </NDropdown>

      <NButton quaternary circle @click="toggleCompactMode" :title="t('apps.compactToggleTooltip')">
        <template #icon><NIcon><component :is="compactMode ? List : LayoutGrid" /></NIcon></template>
      </NButton>

      <div style="margin-left: auto;">
        <NSpace :size="4">
          <NButton
            quaternary circle
            :title="t('apps.restartAutostartTooltip')"
            :disabled="Boolean(bulkActionPending)"
            :loading="bulkActionPending === 'restartAutostart'"
            @click="restartEnabledApps"
          >
            <template #icon><NIcon><RotateCcw /></NIcon></template>
          </NButton>
          <NButton
            quaternary circle
            :title="t('apps.startAutostartTooltip')"
            :disabled="Boolean(bulkActionPending)"
            :loading="bulkActionPending === 'startAutostart'"
            @click="startEnabledApps"
          >
            <template #icon><NIcon><Play /></NIcon></template>
          </NButton>
          <NButton
            quaternary circle type="error"
            :title="t('apps.stopAllTooltip')"
            :disabled="Boolean(bulkActionPending)"
            :loading="bulkActionPending === 'stopAll'"
            @click="stopEveryApp"
          >
            <template #icon><NIcon><Square /></NIcon></template>
          </NButton>
        </NSpace>
      </div>
    </div>

    <NAlert v-if="error" type="error" style="margin-bottom: 24px;">{{ error }}</NAlert>

    <NEmpty v-if="!apps.length && !loading" :description="t('apps.noInstalledApps')" style="margin-top: 48px;" />

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
