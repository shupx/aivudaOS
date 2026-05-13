<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppConfigCenterPage } from '../composables/useAppConfigCenterPage'
import { useDeferredFieldDrafts } from '../composables/useDeferredFieldDrafts'
import MagnetConfigSection from '../components/app-config-center/MagnetConfigSection.vue'
import AppParamsSection from '../components/app-config-center/AppParamsSection.vue'
import UploadInstallModal from '../components/apps/UploadInstallModal.vue'
import { NButton, NIcon, NSpace, NText, NAlert } from 'naive-ui'
import { ArrowLeft, Download, RefreshCw, Plus, Trash2, Upload } from 'lucide-vue-next'

const { t } = useI18n()
const systemColumnWidths = ref([260, 320, 110, 180, 260, 120, 100])
const systemTableWidth = computed(() => systemColumnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
const systemTableWrapRef = ref(null)
const systemHeaderRefs = ref([])
const systemResizeLineLefts = ref([])
let stopSystemColumnResize = null
let systemResizeFrame = 0

const objectEditorRows = computed(() => {
  const text = String(arrayEditorJsonText.value || '')
  const lineCount = text ? text.split('\n').length : 1
  return Math.min(Math.max(lineCount + 1, 8), 28)
})

function startSystemColumnResize(index, event) {
  event.preventDefault()
  const startX = event.clientX
  const startWidth = Number(systemColumnWidths.value[index] || 0)

  const onPointerMove = (moveEvent) => {
    const nextWidth = Math.max(80, startWidth + moveEvent.clientX - startX)
    systemColumnWidths.value = systemColumnWidths.value.map((width, currentIndex) => (
      currentIndex === index ? nextWidth : width
    ))
  }

  const onPointerUp = () => {
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    stopSystemColumnResize = null
  }

  stopSystemColumnResize = onPointerUp
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function setSystemHeaderRef(index) {
  return (element) => {
    systemHeaderRefs.value[index] = element || null
    queueSystemResizeLineUpdate()
  }
}

function updateSystemResizeLines() {
  systemResizeFrame = 0
  const wrap = systemTableWrapRef.value
  if (!wrap) return

  systemResizeLineLefts.value = systemHeaderRefs.value
    .slice(0, -1)
    .map((header) => {
      if (!header) return 0
      return header.offsetLeft + header.offsetWidth - wrap.scrollLeft
    })
}

function queueSystemResizeLineUpdate() {
  if (systemResizeFrame) return
  systemResizeFrame = window.requestAnimationFrame(() => {
    updateSystemResizeLines()
  })
}

function systemRowDraftKey(row) {
  return `${row?.scope || 'sys'}:${row?.appId || '__system__'}:${row?.path || ''}`
}

function getSystemEnumIndexValue(row) {
  return String(getSystemEnumValues(row).findIndex((item) => JSON.stringify(item) === JSON.stringify(getCellValue(row))))
}

onBeforeUnmount(() => {
  if (stopSystemColumnResize) {
    stopSystemColumnResize()
  }
  if (systemResizeFrame) {
    window.cancelAnimationFrame(systemResizeFrame)
    systemResizeFrame = 0
  }
  const wrap = systemTableWrapRef.value
  if (wrap) {
    wrap.removeEventListener('scroll', queueSystemResizeLineUpdate)
  }
  window.removeEventListener('resize', queueSystemResizeLineUpdate)
})

onMounted(() => {
  const wrap = systemTableWrapRef.value
  if (wrap) {
    wrap.addEventListener('scroll', queueSystemResizeLineUpdate, { passive: true })
  }
  window.addEventListener('resize', queueSystemResizeLineUpdate)
  queueSystemResizeLineUpdate()
})

onUpdated(() => {
  queueSystemResizeLineUpdate()
})

watch(systemColumnWidths, async () => {
  await nextTick()
  queueSystemResizeLineUpdate()
}, { deep: true })

const {
  loading,
  error,
  success,
  appOptions,
  selectedAppId,
  appTreeRows,
  systemRows,
  magnets,
  magnetConflicts,
  magnetCollapsed,
  highlightedMagnetPath,
  loadAllConfigs,
  goBackApps,
  setSelectedAppId,
  getCellValue,
  getCellError,
  displayValue,
  getArrayPreviewText,
  getDefaultText,
  getRangeText,
  getDescriptionText,
  getNeedRestartText,
  getRowThemeClass,
  isArrayEditableRow,
  isArrayEditableMagnet,
  openArrayEditorForRow,
  openArrayEditorForMagnet,
  arrayEditorVisible,
  arrayEditorTitle,
  arrayEditorItems,
  arrayEditorPlaceholder,
  arrayEditorMode,
  arrayEditorJsonText,
  arrayEditorValueType,
  arrayEditorCopySuccess,
  toggleArrayEditorMode,
  copyArrayEditorJson,
  closeArrayEditor,
  saveArrayEditor,
  addArrayEditorRow,
  removeArrayEditorRow,
  updateArrayEditorRow,
  isGroupCollapsed,
  toggleGroupCollapsed,
  isAppCollapsed,
  toggleAppCollapsed,
  areAllGroupsCollapsed,
  toggleAllGroupsCollapsed,
  getSystemEnumValues,
  getSystemInputType,
  getSystemValuePlaceholder,
  showSystemAddModal,
  schemaTypeOptions,
  showNewSystemTextInput,
  newSystemValueInputType,
  newSystemPath,
  newSystemValue,
  newSystemBooleanValue,
  newSystemSchemaType,
  newSystemSchemaEnum,
  newSystemSchemaMin,
  newSystemSchemaMax,
  newSystemSchemaMinLength,
  newSystemSchemaMaxLength,
  newSystemSchemaPattern,
  newSystemSchemaItemType,
  newSystemSchemaDescription,
  getMagnetValue,
  getMagnetDisplayValue,
  getMagnetBindingsText,
  onBooleanChange,
  onEnumChange,
  onSystemEnumChange,
  onTextChange,
  openSystemAddModal,
  closeSystemAddModal,
  addSystemParam,
  confirmRemoveSystemParam,
  toggleMagnetCollapsed,
  getMagnetRowId,
  jumpToMagnetByPath,
  onMagnetBooleanChange,
  onMagnetTextChange,
  saveMagnetChanges,
  valueToInlineText,
  needRestartToastVisible,
  needRestartToastMessage,
  exportModalVisible,
  exportIncludeSystem,
  exportSelectedApps,
  exportBusy,
  openExportModal,
  closeExportModal,
  setExportAppSelected,
  exportSelectedConfig,
  importModalVisible,
  importFileName,
  importPreviewSections,
  importCollapsedSections,
  importOverwriteById,
  importOverwriteMagnets,
  importBusy,
  importErrorMessage,
  importSuccessMessage,
  importStoreConnectivityHelpVisible,
  importActionMessage,
  missingImportApps,
  missingAppOptions,
  missingAppBusy,
  missingAppProgress,
  missingAppsCollapsed,
  missingAppColumnSelectionState,
  installAllMissingAppsBusy,
  hasImportOverwriteSelection,
  openImportModal,
  closeImportModal,
  onImportFileChange,
  openOnlineStoreFromImport,
  toggleMissingAppsCollapsed,
  toggleImportSection,
  setImportRowOverwrite,
  isImportSectionOverwriteAllSelected,
  toggleImportSectionOverwrite,
  getImportRowStatusText,
  applyImportSelection,
  setMissingAppOption,
  toggleMissingAppColumn,
  installMissingImportApp,
  installAllMissingImportApps,
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
  closeUploadModal,
  onUploadFileChange,
  submitUpload,
  cancelCurrentUpload,
  submitInteractiveInput,
  setInteractiveInput,
  setInteractiveMaskInput,
} = useAppConfigCenterPage()

const systemTextDrafts = useDeferredFieldDrafts({
  buildKey: systemRowDraftKey,
  getCommittedValue: (row) => displayValue(row),
  commitDraftValue: (row, value) => onTextChange(row, value),
  isEqual: (left, right) => String(left ?? '') === String(right ?? ''),
})

const systemBooleanDrafts = useDeferredFieldDrafts({
  buildKey: systemRowDraftKey,
  getCommittedValue: (row) => Boolean(getCellValue(row)),
  commitDraftValue: (row, value) => onBooleanChange(row, value),
  isEqual: (left, right) => Boolean(left) === Boolean(right),
})

const systemEnumDrafts = useDeferredFieldDrafts({
  buildKey: systemRowDraftKey,
  getCommittedValue: (row) => getSystemEnumIndexValue(row),
  commitDraftValue: (row, value) => onSystemEnumChange(row, value),
  isEqual: (left, right) => String(left ?? '') === String(right ?? ''),
})
</script>

<template>
  <section class="apps-panel app-config-center-page">
    <header class="panel-header app-config-center-header-sticky config-center-shell" style="margin-bottom: 24px;">
      <div class="app-config-center-header-row" style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
        <NSpace align="center">
          <NButton quaternary circle @click="goBackApps" :title="t('appConfigCenter.backToApps')">
             <template #icon><NIcon><ArrowLeft /></NIcon></template>
          </NButton>
          <NText style="font-size: 20px; font-weight: 600;">{{ t('appConfigCenter.title') }}</NText>
        </NSpace>
        <NSpace align="center">
          <NButton secondary size="small" @click="openExportModal">
            <template #icon><NIcon><Upload /></NIcon></template>
            {{ t('appConfigCenter.exportButton') }}
          </NButton>
          <NButton secondary size="small" @click="openImportModal">
            <template #icon><NIcon><Download /></NIcon></template>
            {{ t('appConfigCenter.importButton') }}
          </NButton>
          <NButton secondary size="small" :loading="loading" @click="loadAllConfigs">
            <template #icon><NIcon><RefreshCw /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </div>

      <NAlert v-if="error" type="error" style="margin-top: 12px;">{{ error }}</NAlert>
      <NAlert v-else-if="success" type="success" style="margin-top: 12px;">{{ success }}</NAlert>
    </header>

    <div class="app-config-center-magnet-sticky config-center-shell">
      <MagnetConfigSection
        :magnets="magnets"
        :magnet-conflicts="magnetConflicts"
        :collapsed="magnetCollapsed"
        :highlighted-magnet-path="highlightedMagnetPath"
        :toggle-collapsed="toggleMagnetCollapsed"
        :get-magnet-row-id="getMagnetRowId"
        :get-magnet-value="getMagnetValue"
        :get-magnet-display-value="getMagnetDisplayValue"
        :get-magnet-bindings-text="getMagnetBindingsText"
        :get-array-preview-text="getArrayPreviewText"
        :is-array-editable-magnet="isArrayEditableMagnet"
        :open-array-editor-for-magnet="openArrayEditorForMagnet"
        :on-magnet-boolean-change="onMagnetBooleanChange"
        :on-magnet-text-change="onMagnetTextChange"
        :save-magnet-changes="saveMagnetChanges"
        :value-to-inline-text="valueToInlineText"
      />
    </div>

    <article class="actions-panel config-center-section config-center-shell">
      <header class="log-header">
        <h3>{{ t('appConfigCenter.systemTitle') }}</h3>
      </header>

      <div class="panel-actions wrap config-center-toolbar" style="margin-bottom: 10px;">
        <NButton size="small" type="primary" @click="openSystemAddModal">
          <template #icon><NIcon><Plus /></NIcon></template>
          {{ t('appConfigCenter.systemAdd') }}
        </NButton>
      </div>

      <div v-if="!systemRows.length" class="empty-box">{{ t('appConfigCenter.systemEmpty') }}</div>
      <div ref="systemTableWrapRef" v-else class="table-wrap resizable-table-wrap">
        <table class="config-table compact config-table-resizable" :style="{ width: `${systemTableWidth}px` }">
          <colgroup>
            <col v-for="(width, index) in systemColumnWidths" :key="`sys-col-${index}`" :style="{ width: `${width}px` }">
          </colgroup>
        <thead>
          <tr>
            <th :ref="setSystemHeaderRef(0)">{{ t('appConfigCenter.colPath') }}</th>
            <th :ref="setSystemHeaderRef(1)">{{ t('appConfigCenter.colCurrent') }}</th>
            <th :ref="setSystemHeaderRef(2)">{{ t('appConfigCenter.colType') }}</th>
            <th :ref="setSystemHeaderRef(3)">{{ t('appConfigCenter.colRange') }}</th>
            <th :ref="setSystemHeaderRef(4)">{{ t('appConfigCenter.colDesc') }}</th>
            <th :ref="setSystemHeaderRef(5)">{{ t('appConfigCenter.colNeedRestart') }}</th>
            <th :ref="setSystemHeaderRef(6)">{{ t('appConfigCenter.colAction') }}</th>
          </tr>
        </thead>
          <tbody>
            <tr v-for="row in systemRows" :key="`sys:${row.path}`">
              <td class="mono-cell">{{ row.path }}</td>
              <td>
                <div class="config-edit-cell" :title="row.readonly ? t('appConfigCenter.readonlyInMagnetZone') : ''">
                  <label v-if="row.type === 'boolean'" class="check-item">
                    <input
                      :checked="systemBooleanDrafts.getDraftValue(row)"
                      :disabled="row.readonly"
                      type="checkbox"
                      @change="systemBooleanDrafts.setDraftValue(row, $event?.target?.checked)"
                      @blur="systemBooleanDrafts.commitDraft(row)"
                    >
                    {{ systemBooleanDrafts.getDraftValue(row) ? 'true' : 'false' }}
                  </label>
                  <select
                    v-else-if="getSystemEnumValues(row).length"
                    class="select-input"
                    :disabled="row.readonly"
                    :value="systemEnumDrafts.getDraftValue(row)"
                    @change="systemEnumDrafts.setDraftValue(row, $event?.target?.value)"
                    @blur="systemEnumDrafts.commitDraft(row)"
                  >
                    <option v-for="(item, idx) in getSystemEnumValues(row)" :key="`sys-enum-${row.path}-${idx}`" :value="idx">
                      {{ valueToInlineText(item) }}
                    </option>
                  </select>
                  <button
                    v-else-if="isArrayEditableRow(row)"
                    class="btn btn-array-editor"
                    :disabled="row.readonly"
                    @click="openArrayEditorForRow(row)"
                  >
                    {{ getArrayPreviewText(getCellValue(row)) }}
                  </button>
                  <input
                    v-else
                    class="input"
                    :type="getSystemInputType(row)"
                    :disabled="row.readonly"
                    :placeholder="getSystemValuePlaceholder(row)"
                    :value="systemTextDrafts.getDraftValue(row)"
                    @input="systemTextDrafts.setDraftValue(row, $event?.target?.value || '')"
                    @blur="systemTextDrafts.commitDraft(row)"
                    @keyup.enter="systemTextDrafts.commitDraft(row)"
                  >

                  <template v-if="row.readonly">
                    <button class="link-btn" @click="jumpToMagnetByPath(row.path)">
                      {{ t('appConfigCenter.jumpToMagnet') }}
                    </button>
                  </template>
                  <p v-if="getCellError(row)" class="error-text">{{ t('appConfigCenter.invalidValue') }}: {{ getCellError(row) }}</p>
                </div>
              </td>
              <td>{{ row.type || '-' }}</td>
              <td>{{ row.rangeText || '-' }}</td>
              <td>{{ row.description || '-' }}</td>
              <td>{{ getNeedRestartText(row) }}</td>
              <td>
                <NButton size="small" type="error" quaternary :disabled="row.readonly" @click="confirmRemoveSystemParam(row)" :title="t('appConfigCenter.systemDelete')">
                  <template #icon><NIcon><Trash2 /></NIcon></template>
                </NButton>
              </td>
            </tr>
        </tbody>
      </table>
      <span
        v-for="(left, index) in systemResizeLineLefts"
        :key="`sys-col-line-${index}`"
        class="table-col-resize-line"
        :style="{ left: `${left}px` }"
        @pointerdown="startSystemColumnResize(index, $event)"
      ></span>
      </div>
    </article>

    <div v-if="showSystemAddModal" class="modal-overlay" @click.self="closeSystemAddModal">
      <section class="modal-card">
        <header class="modal-header">
          <h3>{{ t('appConfigCenter.systemAdd') }}</h3>
        </header>

        <div class="field">
          <label>{{ t('appConfigCenter.colPath') }}</label>
          <input
            v-model="newSystemPath"
            class="input"
            :placeholder="t('appConfigCenter.systemPathPlaceholder')"
          >
        </div>

        <div class="field">
          <label>{{ t('appConfigCenter.colCurrent') }}</label>
          <label v-if="newSystemSchemaType === 'boolean'" class="check-item">
            <input
              v-model="newSystemBooleanValue"
              type="checkbox"
            >
            {{ newSystemBooleanValue ? 'true' : 'false' }}
          </label>
          <input
            v-if="showNewSystemTextInput"
            v-model="newSystemValue"
            class="input"
            :type="newSystemValueInputType"
            :placeholder="newSystemSchemaType === 'object' || newSystemSchemaType === 'array' ? t('appConfigCenter.systemValueJsonPlaceholder') : t('appConfigCenter.systemValuePlaceholder')"
          >
        </div>

        <div class="field">
          <label>{{ t('appConfigCenter.colSchema') }}</label>
          <select v-model="newSystemSchemaType" class="select-input">
            <option value="">{{ t('appConfigCenter.schemaTypeNone') }}</option>
            <option v-for="item in schemaTypeOptions" :key="`add-type:${item}`" :value="item">
              {{ item }}
            </option>
          </select>
        </div>

        <div class="field">
          <label>{{ t('appConfigCenter.schemaEnumLabel') }}</label>
          <input
            v-model="newSystemSchemaEnum"
            class="input"
            :placeholder="t('appConfigCenter.schemaEnumPlaceholder')"
          >
        </div>

        <template v-if="newSystemSchemaType === 'integer' || newSystemSchemaType === 'number'">
          <div class="field">
            <label>{{ t('appConfigCenter.schemaMinLabel') }}</label>
            <input
              v-model="newSystemSchemaMin"
              class="input"
              :placeholder="t('appConfigCenter.schemaMinPlaceholder')"
            >
          </div>
          <div class="field">
            <label>{{ t('appConfigCenter.schemaMaxLabel') }}</label>
            <input
              v-model="newSystemSchemaMax"
              class="input"
              :placeholder="t('appConfigCenter.schemaMaxPlaceholder')"
            >
          </div>
        </template>

        <template v-if="newSystemSchemaType === 'string'">
          <div class="field">
            <label>{{ t('appConfigCenter.schemaMinLengthLabel') }}</label>
            <input
              v-model="newSystemSchemaMinLength"
              class="input"
              :placeholder="t('appConfigCenter.schemaMinLengthPlaceholder')"
            >
          </div>
          <div class="field">
            <label>{{ t('appConfigCenter.schemaMaxLengthLabel') }}</label>
            <input
              v-model="newSystemSchemaMaxLength"
              class="input"
              :placeholder="t('appConfigCenter.schemaMaxLengthPlaceholder')"
            >
          </div>
          <div class="field">
            <label>{{ t('appConfigCenter.schemaPatternLabel') }}</label>
            <input
              v-model="newSystemSchemaPattern"
              class="input"
              :placeholder="t('appConfigCenter.schemaPatternPlaceholder')"
            >
          </div>
        </template>

        <div v-if="newSystemSchemaType === 'array'" class="field">
          <label>{{ t('appConfigCenter.schemaItemTypeLabel') }}</label>
          <select v-model="newSystemSchemaItemType" class="select-input">
            <option value="">{{ t('appConfigCenter.schemaItemTypeNone') }}</option>
            <option v-for="item in schemaTypeOptions" :key="`add-item:${item}`" :value="item">
              {{ item }}
            </option>
          </select>
        </div>

        <div class="field">
          <label>{{ t('appConfigCenter.schemaDescriptionLabel') }}</label>
          <input
            v-model="newSystemSchemaDescription"
            class="input"
            :placeholder="t('appConfigCenter.schemaDescriptionPlaceholder')"
          >
        </div>

        <footer class="panel-actions">
          <button class="btn" @click="closeSystemAddModal">{{ t('common.cancel') }}</button>
          <button class="btn primary" @click="addSystemParam">{{ t('appConfigCenter.systemAdd') }}</button>
        </footer>
      </section>
    </div>

    <AppParamsSection
      :app-options="appOptions"
      :selected-app-id="selectedAppId"
      :set-selected-app-id="setSelectedAppId"
      :tree-rows="appTreeRows"
      :get-cell-value="getCellValue"
      :get-cell-error="getCellError"
      :display-value="displayValue"
      :get-array-preview-text="getArrayPreviewText"
      :get-default-text="getDefaultText"
      :get-range-text="getRangeText"
      :get-description-text="getDescriptionText"
      :get-need-restart-text="getNeedRestartText"
      :get-row-theme-class="getRowThemeClass"
      :is-array-editable-row="isArrayEditableRow"
      :open-array-editor-for-row="openArrayEditorForRow"
      :is-group-collapsed="isGroupCollapsed"
      :toggle-group-collapsed="toggleGroupCollapsed"
      :is-app-collapsed="isAppCollapsed"
      :toggle-app-collapsed="toggleAppCollapsed"
      :are-all-groups-collapsed="areAllGroupsCollapsed"
      :toggle-all-groups-collapsed="toggleAllGroupsCollapsed"
      :on-boolean-change="onBooleanChange"
      :on-enum-change="onEnumChange"
      :on-text-change="onTextChange"
      :jump-to-magnet-by-path="jumpToMagnetByPath"
      :value-to-inline-text="valueToInlineText"
    />

    <div v-if="arrayEditorVisible" class="modal-overlay">
      <section
        class="modal-card modal-wide modal-resizable config-array-editor-modal"
        :class="{ 'config-array-editor-modal-object': arrayEditorValueType === 'object' }"
      >
        <header class="modal-header">
          <h3>{{ arrayEditorTitle }}</h3>
            <div class="modal-header-actions" style="display: flex; gap: 4px;">
              <button 
                v-if="arrayEditorValueType === 'array'"
                class="link-btn" 
                style="padding: 4px; display: inline-flex; align-items: center; color: var(--text-color-muted, #888); border: none; background: transparent; outline: none; border-radius: 4px; transition: color 0.2s; cursor: pointer;"
                  @mouseover="$event.currentTarget.style.color='var(--text-color, #333)'" 
                  @mouseout="$event.currentTarget.style.color='var(--text-color-muted, #888)'"
                @click="toggleArrayEditorMode" 
                :title="t('appConfigCenter.arrayEditorToggleJson')"
              >
                <svg v-if="arrayEditorMode === 'rows'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
              </button>
              <button 
                class="link-btn" 
                style="padding: 4px; display: inline-flex; align-items: center; color: var(--text-color-muted, #888); border: none; background: transparent; outline: none; border-radius: 4px; transition: color 0.2s; cursor: pointer;"
                  @mouseenter="!arrayEditorCopySuccess ? $event.currentTarget.style.color='var(--text-color, #333)' : null"
                  @mouseleave="!arrayEditorCopySuccess ? $event.currentTarget.style.color='var(--text-color-muted, #888)' : null"
                :style="arrayEditorCopySuccess ? 'color: var(--success-color, #10b981) !important;' : ''"
                @click="copyArrayEditorJson" 
                :title="t('appConfigCenter.arrayEditorCopyContents')"
              >
                <svg v-if="!arrayEditorCopySuccess" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
              </button>
            </div>
          </header>
        <div class="field config-array-editor-body">
          <template v-if="arrayEditorMode === 'rows'">
            <div class="config-array-editor-list">
              <div v-for="(item, index) in arrayEditorItems" :key="item.id" class="config-array-editor-row">
                <div class="config-array-editor-index">{{ index + 1 }}</div>
                <textarea
                  class="text-area config-array-editor-item"
                  :placeholder="arrayEditorPlaceholder"
                  :value="item.text"
                  @input="updateArrayEditorRow(item.id, $event?.target?.value || ''); $event.target.style.height = 'auto'; $event.target.style.height = `${$event.target.scrollHeight}px`"
                  @focus="$event.target.style.height = 'auto'; $event.target.style.height = `${$event.target.scrollHeight}px`"
                ></textarea>
                <button
                  class="btn config-array-editor-remove"
                  :disabled="arrayEditorItems.length <= 1"
                  @click="removeArrayEditorRow(item.id)"
                  :title="t('appConfigCenter.arrayEditorRemoveRow')"
                >
                  -
                </button>
              </div>
            </div>
            <div class="panel-actions">
              <button class="btn config-array-editor-add" :title="t('appConfigCenter.arrayEditorAddRow')" @click="addArrayEditorRow">
                +
              </button>
            </div>
          </template>
          <template v-else>
            <textarea
              class="text-area config-array-editor-json"
              v-model="arrayEditorJsonText"
              :rows="objectEditorRows"
            ></textarea>
          </template>
        </div>

        <div class="panel-actions wrap">
          <button class="btn primary" @click="saveArrayEditor">{{ t('appConfigCenter.arrayEditorSave') }}</button>
          <button class="btn" @click="closeArrayEditor">{{ t('appConfigCenter.arrayEditorExit') }}</button>
        </div>
      </section>
    </div>

    <div v-if="needRestartToastVisible" class="side-toast side-toast-info">
      {{ needRestartToastMessage }}
    </div>

    <div v-if="exportModalVisible" class="modal-overlay" @click.self="closeExportModal">
      <section class="modal-card modal-wide">
        <header class="modal-header">
          <h3>{{ t('appConfigCenter.exportTitle') }}</h3>
        </header>
        <div class="config-transfer-list">
          <label class="check-item">
            <input v-model="exportIncludeSystem" type="checkbox">
            {{ t('appConfigCenter.systemTitle') }}
          </label>
          <label
            v-for="item in appOptions"
            :key="`export-app:${item.appId}`"
            class="check-item"
          >
            <input
              type="checkbox"
              :checked="exportSelectedApps[item.appId] !== false"
              @change="setExportAppSelected(item.appId, $event?.target?.checked)"
            >
            {{ item.name }} ({{ item.appId }} @ {{ item.version }})
          </label>
        </div>
        <footer class="panel-actions">
          <button class="btn" :disabled="exportBusy" @click="closeExportModal">{{ t('common.cancel') }}</button>
          <button class="btn primary" :disabled="exportBusy" @click="exportSelectedConfig">
            {{ exportBusy ? t('appConfigCenter.exporting') : t('appConfigCenter.exportButton') }}
          </button>
        </footer>
      </section>
    </div>

    <div v-if="importModalVisible" class="modal-overlay">
      <section class="modal-card modal-wide modal-resizable config-import-modal-card">
        <header class="modal-header">
          <h3>{{ t('appConfigCenter.importTitle') }}</h3>
        </header>

        <div class="field">
          <label>{{ t('appConfigCenter.importFile') }}</label>
          <input
            class="input"
            type="file"
            accept="application/json,.json"
            @change="onImportFileChange($event?.target?.files)"
          >
          <span v-if="importFileName" class="muted">{{ importFileName }}</span>
        </div>

        <div v-if="missingImportApps.length" class="config-transfer-missing">
          <div class="config-transfer-missing-header">
            <button class="config-transfer-missing-toggle" @click="toggleMissingAppsCollapsed">
              <span>{{ missingAppsCollapsed ? '+' : '-' }}</span>
              <h4>{{ t('appConfigCenter.importMissingApps') }}</h4>
              <span class="muted">{{ missingImportApps.length }}</span>
            </button>
            <div class="config-transfer-missing-actions">
              <button
                class="btn"
                :disabled="installAllMissingAppsBusy"
                @click="installAllMissingImportApps"
              >
                {{ installAllMissingAppsBusy ? t('store.downloading') : t('appConfigCenter.importInstallAllMissingApps') }}
              </button>
            </div>
          </div>
          <div v-if="!missingAppsCollapsed" class="table-wrap config-transfer-missing-table-wrap">
            <table class="config-table compact config-transfer-missing-table">
              <thead>
                <tr>
                  <th :title="t('appConfigCenter.importAppTip')">{{ t('appConfigCenter.colApp') }}</th>
                  <th
                    class="config-transfer-th-toggle"
                    :title="t('appConfigCenter.importInstallTip')"
                    @click="toggleMissingAppColumn('autoDownload')"
                  >
                    {{ t('appConfigCenter.importInstall') }}
                  </th>
                  <th
                    class="config-transfer-th-toggle"
                    :title="t('appConfigCenter.importAllowNameMatchTip')"
                    @click="toggleMissingAppColumn('allowNameMatch')"
                  >
                    {{ t('appConfigCenter.importAllowNameMatch') }}
                  </th>
                  <th
                    class="config-transfer-th-toggle"
                    :title="t('appConfigCenter.importUseLatestTip')"
                    @click="toggleMissingAppColumn('latest')"
                  >
                    {{ t('appConfigCenter.importUseLatest') }}
                  </th>
                  <th :title="t('appConfigCenter.importActionTip')">{{ t('appConfigCenter.colAction') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="app in missingImportApps" :key="`missing:${app.appId}`">
                  <td>
                    <strong>{{ app.name }}</strong>
                    <span class="muted"> ({{ app.appId }} @ {{ app.version || '-' }})</span>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      :checked="missingAppOptions[app.appId]?.autoDownload !== false"
                      @change="setMissingAppOption(app.appId, 'autoDownload', $event?.target?.checked)"
                    >
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      :checked="missingAppOptions[app.appId]?.allowNameMatch === true"
                      @change="setMissingAppOption(app.appId, 'allowNameMatch', $event?.target?.checked)"
                    >
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      :checked="missingAppOptions[app.appId]?.latest === true"
                      @change="setMissingAppOption(app.appId, 'latest', $event?.target?.checked)"
                    >
                  </td>
                  <td>
                    <button
                      class="btn"
                      :disabled="missingAppBusy[app.appId] || missingAppOptions[app.appId]?.autoDownload === false"
                      @click="installMissingImportApp(app.appId)"
                    >
                      {{ missingAppBusy[app.appId] ? t('store.downloading') : t('appConfigCenter.importInstallMissingApp') }}
                    </button>
                    <div v-if="missingAppProgress[app.appId]" class="download-progress">
                      <div class="download-progress-track">
                        <div class="download-progress-bar" :style="{ width: `${missingAppProgress[app.appId]}%` }"></div>
                      </div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <label class="check-item">
          <input v-model="importOverwriteMagnets" type="checkbox">
          {{ t('appConfigCenter.importOverwriteMagnets') }}
        </label>

        <NAlert v-if="importErrorMessage" type="error" style="margin-top: 12px;">
          <div>{{ importErrorMessage }}</div>
          <div v-if="importStoreConnectivityHelpVisible" class="config-import-store-help">
            <span>{{ t('appConfigCenter.importStoreConnectivityHelp') }}</span>
            <button class="btn linklike" @click="openOnlineStoreFromImport">
              {{ t('common.onlineStore') }}
            </button>
          </div>
        </NAlert>
        <NAlert v-else-if="importSuccessMessage" type="success" style="margin-top: 12px;">
          {{ importSuccessMessage }}
        </NAlert>

        <div v-if="importActionMessage" class="success-text">{{ importActionMessage }}</div>

        <div v-if="importPreviewSections.length" class="config-import-preview">
          <section
            v-for="section in importPreviewSections"
            :key="section.id"
            class="config-import-section"
          >
            <button class="config-import-section-header" @click="toggleImportSection(section.id)">
              <span>{{ importCollapsedSections[section.id] ? '+' : '-' }}</span>
              <div class="config-import-section-header-main">
                <strong>{{ section.title }}</strong>
                <span
                  v-if="section.hasVersionMismatch"
                  class="muted config-import-version-mismatch"
                >
                  {{ t('appConfigCenter.importVersionMismatchHint', {
                    currentVersion: section.currentVersion || '-',
                    importedVersion: section.importedVersion || '-',
                  }) }}
                </span>
              </div>
              <span class="muted">
                {{ section.visibleRows.length }}/{{ section.rows.length }}
              </span>
            </button>
            <div v-if="section.visibleRows.length" class="table-wrap config-import-table-wrap">
              <table class="config-table compact config-import-table">
                <thead>
                  <tr>
                    <th>{{ t('appConfigCenter.colPath') }}</th>
                    <th>{{ t('appConfigCenter.importValue') }}</th>
                    <th>{{ t('appConfigCenter.importCurrentValue') }}</th>
                    <th
                      class="config-transfer-th-toggle"
                      @click="toggleImportSectionOverwrite(section.id)"
                    >
                      {{ t('appConfigCenter.importOverwrite') }}
                      <span class="muted">
                        {{ isImportSectionOverwriteAllSelected(section.id) ? ' (all)' : '' }}
                      </span>
                    </th>
                    <th>{{ t('appConfigCenter.importStatus') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in section.visibleRows"
                    :key="row.id"
                    :class="{ 'config-import-row-highlight': row.status !== 'same' }"
                  >
                    <td class="mono-cell">{{ row.path }}</td>
                    <td class="mono-cell">{{ row.importText }}</td>
                    <td class="mono-cell">{{ row.currentText }}</td>
                    <td>
                      <input
                        type="checkbox"
                        :checked="importOverwriteById[row.id] === true"
                        :disabled="!row.canOverwrite || (row.isMagnet && !importOverwriteMagnets)"
                        @change="setImportRowOverwrite(row.id, $event?.target?.checked)"
                      >
                    </td>
                    <td>{{ getImportRowStatusText(row) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-box">{{ t('appConfigCenter.importOnlySameValuesHidden') }}</div>
          </section>
        </div>
        <div v-else class="empty-box">{{ t('appConfigCenter.importNoPreview') }}</div>

        <footer class="panel-actions">
          <button class="btn" :disabled="importBusy" @click="closeImportModal">{{ t('common.cancel') }}</button>
          <button class="btn primary" :disabled="importBusy || !hasImportOverwriteSelection" @click="applyImportSelection">
            {{ importBusy ? t('appConfigCenter.importApplying') : t('appConfigCenter.importApply') }}
          </button>
        </footer>
      </section>
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
      @interactive-submit="submitInteractiveInput"
      @interactive-input="setInteractiveInput"
      @interactive-mask-change="setInteractiveMaskInput"
    />

  </section>
</template>
