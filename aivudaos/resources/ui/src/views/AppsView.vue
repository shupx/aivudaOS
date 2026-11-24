<script setup>
import { computed, defineAsyncComponent, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import AppGroupSection from '../components/apps/AppGroupSection.vue'
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
  NTab,
  NTabs
} from 'naive-ui'
import {
  Upload,
  RefreshCw,
  Search,
  Layers,
  ArrowUpDown,
  LayoutGrid,
  List,
  RotateCcw,
  Play,
  Square
} from 'lucide-vue-next'

const StartupPipelinePanel = defineAsyncComponent(() => import('../components/apps/StartupPipelinePanel.vue'))
const view = ref('apps')
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
  setSortOption,
  searchResults,
  searchDropdownVisible,
  activeSearchIndex,
  highlightedAppId,
  jumpToAppCard,
  openSearchDropdown,
  handleSearchKeydown,
  refresh,
  toggleCompactMode,
  isFavoriteApp,
  toggleFavoriteApp,
  busyById,
  restartBusyById,
  toggleRunning,
  toggleAutostart,
  restartSingleApp,
  restartRunningApps,
  startEnabledApps,
  stopEveryApp,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadStatus,
  uploadStatusDone,
  uploadWarning,
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
  listSections, hasPipelineGroups, groupedView, pipelineGroupName,
  pipelineBusy, pipelineOperation, pipelineCancelPending, pipelineError, pipelineConfigReady, pipelineConfigLoading,
  runGroup, restartGroup, stopGroup, runDefaultPipeline, restartDefaultPipeline, stopDefaultPipeline,
  cancelPipelineOperation, refreshList, acceptPipelineConfig, operationRevision,
} = useAppsPanel(view)

const editor = ref(null)
const listControlsDisabled = computed(() => !pipelineConfigReady.value || pipelineBusy.value || Boolean(bulkActionPending.value))
async function beforeTabChange(_next, current) {
  if (current === 'pipeline') await editor.value?.flush()
  return true
}

const sortOptions = computed(() => [
  { label: t('apps.sortByName') + (sortOption.value === 'name' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'name' },
  { label: t('apps.sortByAutostart') + (sortOption.value === 'autostart' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'autostart' },
  { label: t('apps.sortByInstallationTime') + (sortOption.value === 'installed_at' ? (sortDesc.value ? ' ↓' : ' ↑') : ''), key: 'installed_at' },
])

</script>

<template>
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; gap: 12px; flex-wrap: wrap;">
      <NSpace align="center">
        <NText style="font-size: 20px; font-weight: 600;">{{ t('apps.title') }}</NText>
        <NButton v-if="view === 'apps'" secondary size="small" :loading="loading || pipelineConfigLoading" @click="refreshList">
          <template #icon><NIcon><RefreshCw /></NIcon></template>
          {{ t('common.refresh') }}
        </NButton>
      </NSpace>
      <NButton type="primary" size="small" class="apps-upload-btn" @click="openUploadModal">
        <template #icon><NIcon><Upload /></NIcon></template>
        <span class="apps-upload-btn-label">{{ t('apps.uploadLink') }}</span>
      </NButton>
    </div>

    <NTabs v-model:value="view" :on-before-leave="beforeTabChange" type="line" style="margin-bottom: 20px;">
      <NTab name="apps">{{ t('pipeline.appList') }}</NTab>
      <NTab name="pipeline">{{ t('pipeline.title') }}</NTab>
    </NTabs>
    <KeepAlive>
      <StartupPipelinePanel v-if="view === 'pipeline'" ref="editor" :apps="apps" :operation-revision="operationRevision"
        @saved="acceptPipelineConfig" @operation-finished="refresh" />
    </KeepAlive>
    <template v-if="view === 'apps'">
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap;">
      <div class="apps-search-box" style="position: relative; width: 320px; max-width: 100%;">
        <NInput
          v-model:value="searchText"
          :input-props="{ name: 'apps-search', autocomplete: 'on' }"
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

      <NDropdown v-if="!groupedView" trigger="click" :options="sortOptions" @select="setSortOption">
        <NButton quaternary circle>
          <template #icon><NIcon><ArrowUpDown /></NIcon></template>
        </NButton>
      </NDropdown>

      <NButton quaternary circle @click="toggleCompactMode" :title="t('apps.compactToggleTooltip')">
        <template #icon><NIcon><component :is="compactMode ? List : LayoutGrid" /></NIcon></template>
      </NButton>

      <NButton v-if="hasPipelineGroups" size="small" secondary :type="groupedView ? 'primary' : 'default'"
        :aria-pressed="groupedView" :title="t(groupedView ? 'apps.pipelineGroups.flatView' : 'apps.pipelineGroups.groupedView')"
        @click="groupedView = !groupedView">
        <template #icon><NIcon><Layers /></NIcon></template>{{ t('apps.pipelineGroups.groupedView') }}
      </NButton>

      <div style="margin-left: auto;">
        <NSpace v-if="pipelineOperation && !pipelineOperation.done" align="center" :size="8">
          <span role="status">{{ t(`pipeline.states.${pipelineOperation.status}`) }}</span>
          <NButton size="small" :disabled="pipelineCancelPending" @click="cancelPipelineOperation">{{ t('pipeline.cancelRun') }}</NButton>
        </NSpace>
        <NSpace v-else-if="hasPipelineGroups" :size="4">
          <NButton quaternary circle :disabled="listControlsDisabled"
            :title="t('apps.pipelineGroups.startDefault')" :aria-label="t('apps.pipelineGroups.startDefault')" @click="runDefaultPipeline">
            <template #icon><NIcon><Play /></NIcon></template>
          </NButton>
          <NButton quaternary circle :disabled="listControlsDisabled"
            :title="t('apps.pipelineGroups.restartDefault')" :aria-label="t('apps.pipelineGroups.restartDefault')" @click="restartDefaultPipeline">
            <template #icon><NIcon><RotateCcw /></NIcon></template>
          </NButton>
          <NButton quaternary circle :disabled="listControlsDisabled"
            :title="t('apps.pipelineGroups.stopDefault')" :aria-label="t('apps.pipelineGroups.stopDefault')" @click="stopDefaultPipeline">
            <template #icon><NIcon><Square /></NIcon></template>
          </NButton>
        </NSpace>
        <NSpace v-else-if="pipelineConfigReady && !pipelineConfigLoading" :size="4">
          <NButton
            quaternary circle
            :title="t('apps.restartRunningTooltip')"
            :disabled="Boolean(bulkActionPending)"
            :loading="bulkActionPending === 'restartRunning'"
            @click="restartRunningApps"
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

    <NAlert v-if="pipelineError" type="error" style="margin-bottom: 16px;">{{ pipelineError }}</NAlert>
    <NEmpty v-if="!apps.length && !loading" :description="t('apps.noInstalledApps')" style="margin-top: 48px;" />

    <AppGroupSection v-for="section in listSections" :key="section.group ? `group:${section.group.id}` : 'apps'"
      :section="section" :name="section.group ? pipelineGroupName(section.group) : ''"
      :busy="listControlsDisabled" :cancel-pending="pipelineCancelPending"
      @run="runGroup" @restart="restartGroup" @stop="stopGroup" @cancel="cancelPipelineOperation">
      <div class="apps-grid" :class="{ 'apps-grid-compact': compactMode }">
        <AppCard
          v-for="app in section.apps"
          :key="app.app_id"
          :app="app"
          :busy="Boolean(busyById[app.app_id])"
          :restart-busy="Boolean(restartBusyById[app.app_id])"
          :card-id="`app-card-${app.app_id}`"
          :highlighted="highlightedAppId === app.app_id"
          :compact="compactMode"
          :favorite="isFavoriteApp(app)"
          show-restart
          @toggle-running="toggleRunning"
          @toggle-autostart="toggleAutostart"
          @toggle-favorite="toggleFavoriteApp"
          @restart-app="restartSingleApp"
        />
      </div>
    </AppGroupSection>

    </template>

    <UploadInstallModal
      :visible="showUploadModal"
      :busy="uploadBusy"
      :error="uploadError"
      :status="uploadStatus"
      :status-done="uploadStatusDone"
      :warning="uploadWarning"
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
