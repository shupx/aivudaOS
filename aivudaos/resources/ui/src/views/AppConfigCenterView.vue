<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppConfigCenterPage } from '../composables/useAppConfigCenterPage'
import MagnetConfigSection from '../components/app-config-center/MagnetConfigSection.vue'
import AppParamsSection from '../components/app-config-center/AppParamsSection.vue'

const { t } = useI18n()
const systemColumnWidths = ref([260, 320, 110, 180, 120, 260, 100])
const systemTableWidth = computed(() => systemColumnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
const systemTableWrapRef = ref(null)
const systemHeaderRefs = ref([])
const systemResizeLineLefts = ref([])
let stopSystemColumnResize = null
let systemResizeFrame = 0

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
} = useAppConfigCenterPage()
</script>

<template>
  <section class="apps-panel app-config-center-page">
    <header class="panel-header app-config-center-header-sticky">
      <div class="app-config-center-header-row">
        <h2>{{ t('appConfigCenter.title') }}</h2>
        <div class="panel-actions wrap">
          <button class="btn" @click="goBackApps">{{ t('appConfigCenter.backToApps') }}</button>
          <button class="btn btn-stable-refresh" :disabled="loading" @click="loadAllConfigs">
            {{ loading ? t('common.loadingShort') : t('common.refresh') }}
          </button>
        </div>
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>
      <p v-else-if="success" class="ok-text">{{ success }}</p>
    </header>

    <div class="app-config-center-magnet-sticky">
      <MagnetConfigSection
        :magnets="magnets"
        :magnet-conflicts="magnetConflicts"
        :collapsed="magnetCollapsed"
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

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfigCenter.systemTitle') }}</h3>
      </header>

      <div class="panel-actions wrap" style="margin-bottom: 10px;">
        <button class="btn" @click="openSystemAddModal">{{ t('appConfigCenter.systemAdd') }}</button>
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
            <th :ref="setSystemHeaderRef(4)">{{ t('appConfigCenter.colNeedRestart') }}</th>
            <th :ref="setSystemHeaderRef(5)">{{ t('appConfigCenter.colDesc') }}</th>
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
                      :checked="Boolean(getCellValue(row))"
                      :disabled="row.readonly"
                      type="checkbox"
                      @change="onBooleanChange(row, $event?.target?.checked)"
                    >
                    {{ Boolean(getCellValue(row)) ? 'true' : 'false' }}
                  </label>
                  <select
                    v-else-if="getSystemEnumValues(row).length"
                    class="select-input"
                    :disabled="row.readonly"
                    :value="getSystemEnumValues(row).findIndex((item) => JSON.stringify(item) === JSON.stringify(getCellValue(row)))"
                    @change="onSystemEnumChange(row, $event?.target?.value)"
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
                    :value="displayValue(row)"
                    @change="onTextChange(row, $event?.target?.value || '')"
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
              <td>{{ getNeedRestartText(row) }}</td>
              <td>{{ row.description || '-' }}</td>
              <td>
                <button class="btn" :disabled="row.readonly" @click="confirmRemoveSystemParam(row)">
                  {{ t('appConfigCenter.systemDelete') }}
                </button>
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
      <section class="modal-card modal-wide modal-resizable config-array-editor-modal">
        <header class="modal-header">
          <h3>{{ arrayEditorTitle }}</h3>
        </header>

        <div class="field">
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

  </section>
</template>
