<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const columnWidths = ref([260, 320, 180, 110, 180, 120, 260])
const totalTableWidth = computed(() => columnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
const tableWrapRef = ref(null)
const tableRef = ref(null)
const headerRefs = ref([])
const resizeLineLefts = ref([])
let stopColumnResize = null
let resizeFrame = 0

function startColumnResize(index, event) {
  event.preventDefault()
  const startX = event.clientX
  const startWidth = Number(columnWidths.value[index] || 0)

  const onPointerMove = (moveEvent) => {
    const nextWidth = Math.max(80, startWidth + moveEvent.clientX - startX)
    columnWidths.value = columnWidths.value.map((width, currentIndex) => (
      currentIndex === index ? nextWidth : width
    ))
  }

  const onPointerUp = () => {
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    stopColumnResize = null
  }

  stopColumnResize = onPointerUp
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function setHeaderRef(index) {
  return (element) => {
    headerRefs.value[index] = element || null
    queueResizeLineUpdate()
  }
}

function updateResizeLines() {
  resizeFrame = 0
  const wrap = tableWrapRef.value
  if (!wrap) return

  resizeLineLefts.value = headerRefs.value
    .slice(0, -1)
    .map((header) => {
      if (!header) return 0
      return header.offsetLeft + header.offsetWidth - wrap.scrollLeft
    })
}

function queueResizeLineUpdate() {
  if (resizeFrame) return
  resizeFrame = window.requestAnimationFrame(() => {
    updateResizeLines()
  })
}

onBeforeUnmount(() => {
  if (stopColumnResize) {
    stopColumnResize()
  }
  if (resizeFrame) {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = 0
  }
  const wrap = tableWrapRef.value
  if (wrap) {
    wrap.removeEventListener('scroll', queueResizeLineUpdate)
  }
  window.removeEventListener('resize', queueResizeLineUpdate)
})

onMounted(() => {
  const wrap = tableWrapRef.value
  if (wrap) {
    wrap.addEventListener('scroll', queueResizeLineUpdate, { passive: true })
  }
  window.addEventListener('resize', queueResizeLineUpdate)
  queueResizeLineUpdate()
})

onUpdated(() => {
  queueResizeLineUpdate()
})

watch(columnWidths, async () => {
  await nextTick()
  queueResizeLineUpdate()
}, { deep: true })

defineProps({
  appOptions: { type: Array, default: () => [] },
  selectedAppId: { type: String, default: '' },
  setSelectedAppId: { type: Function, required: true },
  treeRows: { type: Array, default: () => [] },
  getCellValue: { type: Function, required: true },
  getCellError: { type: Function, required: true },
  displayValue: { type: Function, required: true },
  getArrayPreviewText: { type: Function, required: true },
  getDefaultText: { type: Function, required: true },
  getRangeText: { type: Function, required: true },
  getDescriptionText: { type: Function, required: true },
  getNeedRestartText: { type: Function, required: true },
  getRowThemeClass: { type: Function, required: true },
  isArrayEditableRow: { type: Function, required: true },
  openArrayEditorForRow: { type: Function, required: true },
  isGroupCollapsed: { type: Function, required: true },
  toggleGroupCollapsed: { type: Function, required: true },
  isAppCollapsed: { type: Function, required: true },
  toggleAppCollapsed: { type: Function, required: true },
  areAllGroupsCollapsed: { type: Function, required: true },
  toggleAllGroupsCollapsed: { type: Function, required: true },
  onBooleanChange: { type: Function, required: true },
  onEnumChange: { type: Function, required: true },
  onTextChange: { type: Function, required: true },
  jumpToMagnetByPath: { type: Function, required: true },
  valueToInlineText: { type: Function, required: true },
})
</script>

<template>
  <article class="actions-panel">
    <header class="log-header">
      <h3>{{ t('appConfigCenter.tableTitle') }}</h3>
    </header>

    <div class="panel-actions wrap">
      <button class="tree-toggle-btn" :title="areAllGroupsCollapsed() ? t('appConfigCenter.expand') : t('appConfigCenter.collapse')" @click="toggleAllGroupsCollapsed">
        {{ areAllGroupsCollapsed() ? '+' : '-' }}
      </button>
      <label class="muted" for="config-center-app-select-inline">{{ t('appConfigCenter.filterApp') }}</label>
      <select
        id="config-center-app-select-inline"
        class="select-input"
        :value="selectedAppId"
        @change="setSelectedAppId($event?.target?.value || '')"
      >
        <option value="">{{ t('appConfigCenter.filterAll') }}</option>
        <option v-for="item in appOptions" :key="item.appId" :value="item.appId">
          {{ item.name }} ({{ item.appId }} @ {{ item.version }})
        </option>
      </select>
    </div>

    <div v-if="!treeRows.length" class="empty-box">{{ t('appConfigCenter.empty') }}</div>

    <div ref="tableWrapRef" v-else class="table-wrap resizable-table-wrap">
      <table ref="tableRef" class="config-table config-table-resizable" :style="{ width: `${totalTableWidth}px` }">
        <colgroup>
          <col v-for="(width, index) in columnWidths" :key="`app-col-${index}`" :style="{ width: `${width}px` }">
        </colgroup>
        <thead>
          <tr>
            <th :ref="setHeaderRef(0)">{{ t('appConfigCenter.colPath') }}</th>
            <th :ref="setHeaderRef(1)">{{ t('appConfigCenter.colCurrent') }}</th>
            <th :ref="setHeaderRef(2)">{{ t('appConfigCenter.colDefault') }}</th>
            <th :ref="setHeaderRef(3)">{{ t('appConfigCenter.colType') }}</th>
            <th :ref="setHeaderRef(4)">{{ t('appConfigCenter.colRange') }}</th>
            <th :ref="setHeaderRef(5)">{{ t('appConfigCenter.colNeedRestart') }}</th>
            <th :ref="setHeaderRef(6)">{{ t('appConfigCenter.colDesc') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in treeRows" :key="item.id">
            <tr
              v-if="item.type === 'app-title'"
              class="config-app-title-row"
              :class="getRowThemeClass(item.appId)"
            >
              <td colspan="7">
                <div class="config-app-title-cell">
                  <button class="tree-toggle-btn" :title="isAppCollapsed(item.appId) ? t('appConfigCenter.expand') : t('appConfigCenter.collapse')" @click="toggleAppCollapsed(item.appId)">
                    {{ isAppCollapsed(item.appId) ? '+' : '-' }}
                  </button>
                  <span>{{ item.appName }} ({{ item.appId }} @ {{ item.appVersion || '-' }})</span>
                </div>
              </td>
            </tr>

            <tr
              v-else-if="item.type === 'group'"
              class="config-group-row"
              :class="getRowThemeClass(item.appId)"
            >
              <td class="mono-cell">
                <div class="config-tree-path" :style="{ paddingLeft: `${item.depth * 20}px` }">
                  <button class="tree-toggle-btn" :title="isGroupCollapsed(item.id) ? t('appConfigCenter.expand') : t('appConfigCenter.collapse')" @click="toggleGroupCollapsed(item.id)">
                    {{ isGroupCollapsed(item.id) ? '+' : '-' }}
                  </button>
                  <span class="config-group-label" :class="{ 'config-default-changed-label': item.defaultChanged }">{{ item.label }}</span>
                </div>
              </td>
              <td colspan="6"></td>
            </tr>

            <tr v-else :class="getRowThemeClass(item.row.appId)">
              <td class="mono-cell">
                <div class="config-tree-path" :style="{ paddingLeft: `${item.depth * 20}px` }">
                  <span class="config-leaf-label" :class="{ 'config-default-changed-label': item.defaultChanged }">{{ item.label }}</span>
                </div>
              </td>
              <td>
                <div
                  class="config-edit-cell"
                  :class="{ 'config-default-changed-value': item.defaultChanged }"
                  :title="item.row.readonly ? t('appConfigCenter.readonlyInMagnetZone') : ''"
                >
                  <label v-if="item.row.type === 'boolean'" class="check-item" :class="{ 'config-default-changed-value': item.defaultChanged }">
                    <input
                      :checked="Boolean(getCellValue(item.row))"
                      :disabled="item.row.readonly"
                      type="checkbox"
                      @change="onBooleanChange(item.row, $event?.target?.checked)"
                    >
                    {{ Boolean(getCellValue(item.row)) ? 'true' : 'false' }}
                  </label>

                  <select
                    v-else-if="Array.isArray(item.row.enumValues) && item.row.enumValues.length"
                    class="select-input"
                    :class="{ 'config-default-changed-value': item.defaultChanged }"
                    :disabled="item.row.readonly"
                    :value="item.row.enumValues.findIndex((enumItem) => JSON.stringify(enumItem) === JSON.stringify(getCellValue(item.row)))"
                    @change="onEnumChange(item.row, $event?.target?.value)"
                  >
                    <option v-for="(enumItem, idx) in item.row.enumValues" :key="idx" :value="idx">
                      {{ valueToInlineText(enumItem) }}
                    </option>
                  </select>

                  <button
                    v-else-if="isArrayEditableRow(item.row)"
                    class="btn btn-array-editor"
                    :class="{ 'config-default-changed-value': item.defaultChanged }"
                    :disabled="item.row.readonly"
                    @click="openArrayEditorForRow(item.row)"
                  >
                    {{ getArrayPreviewText(getCellValue(item.row)) }}
                  </button>

                  <input
                    v-else
                    class="input"
                    :class="{ 'config-default-changed-value': item.defaultChanged }"
                    :disabled="item.row.readonly"
                    :value="displayValue(item.row)"
                    @change="onTextChange(item.row, $event?.target?.value || '')"
                  >

                  <template v-if="item.row.readonly">
                    <button class="link-btn" @click="jumpToMagnetByPath(item.row.path)">
                      {{ t('appConfigCenter.jumpToMagnet') }}
                    </button>
                  </template>
                  <p v-if="getCellError(item.row)" class="error-text">{{ t('appConfigCenter.invalidValue') }}: {{ getCellError(item.row) }}</p>
                </div>
              </td>
              <td class="mono-cell">{{ getDefaultText(item.row) }}</td>
              <td>{{ item.row.type || '-' }}</td>
              <td>{{ getRangeText(item.row) }}</td>
              <td>{{ getNeedRestartText(item.row) }}</td>
              <td>{{ getDescriptionText(item.row) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
      <span
        v-for="(left, index) in resizeLineLefts"
        :key="`app-col-line-${index}`"
        class="table-col-resize-line"
        :style="{ left: `${left}px` }"
        @pointerdown="startColumnResize(index, $event)"
      ></span>
    </div>
  </article>
</template>
