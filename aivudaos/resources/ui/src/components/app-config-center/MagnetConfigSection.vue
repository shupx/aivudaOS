<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const columnWidths = ref([260, 320, 120, 320])
const totalTableWidth = computed(() => columnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
const tableWrapRef = ref(null)
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
  magnets: { type: Array, default: () => [] },
  magnetConflicts: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: true },
  toggleCollapsed: { type: Function, required: true },
  getMagnetRowId: { type: Function, required: true },
  getMagnetValue: { type: Function, required: true },
  getMagnetDisplayValue: { type: Function, required: true },
  getMagnetBindingsText: { type: Function, required: true },
  getArrayPreviewText: { type: Function, required: true },
  isArrayEditableMagnet: { type: Function, required: true },
  openArrayEditorForMagnet: { type: Function, required: true },
  onMagnetBooleanChange: { type: Function, required: true },
  onMagnetTextChange: { type: Function, required: true },
  saveMagnetChanges: { type: Function, required: true },
  valueToInlineText: { type: Function, required: true },
})
</script>

<template>
  <article class="actions-panel">
    <header class="log-header">
      <div class="panel-actions panel-title-actions">
        <h3>{{ t('appConfigCenter.magnetTitle') }}</h3>
        <button class="btn" @click="toggleCollapsed">
          {{ collapsed ? t('appConfigCenter.expand') : t('appConfigCenter.collapse') }}
        </button>
      </div>
    </header>

    <p class="muted">{{ t('appConfigCenter.magnetDesc') }}</p>

    <div v-if="collapsed" class="muted"></div>
    <div v-else-if="!magnets.length" class="empty-box">{{ t('appConfigCenter.magnetEmpty') }}</div>
    <div ref="tableWrapRef" v-else class="table-wrap resizable-table-wrap">
      <table class="config-table compact config-table-resizable" :style="{ width: `${totalTableWidth}px` }">
        <colgroup>
          <col v-for="(width, index) in columnWidths" :key="`magnet-col-${index}`" :style="{ width: `${width}px` }">
        </colgroup>
        <thead>
          <tr>
            <th :ref="setHeaderRef(0)">{{ t('appConfigCenter.colPath') }}</th>
            <th :ref="setHeaderRef(1)">{{ t('appConfigCenter.colCurrent') }}</th>
            <th :ref="setHeaderRef(2)">{{ t('appConfigCenter.colType') }}</th>
            <th :ref="setHeaderRef(3)">{{ t('appConfigCenter.magnetBindings') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in magnets" :id="getMagnetRowId(group.path)" :key="group.group_id">
            <td class="mono-cell">{{ group.path }}</td>
            <td>
              <label v-if="group.value_type === 'boolean'" class="check-item">
                <input
                  :checked="Boolean(getMagnetValue(group))"
                  type="checkbox"
                  @change="onMagnetBooleanChange(group, $event?.target?.checked); saveMagnetChanges(group)"
                >
                {{ Boolean(getMagnetValue(group)) ? 'true' : 'false' }}
              </label>
              <button
                v-else-if="isArrayEditableMagnet(group)"
                class="btn btn-array-editor"
                @click="openArrayEditorForMagnet(group)"
              >
                {{ getArrayPreviewText(getMagnetValue(group)) }}
              </button>
              <input
                v-else
                class="input"
                :value="getMagnetDisplayValue(group)"
                @change="onMagnetTextChange(group, $event?.target?.value || ''); saveMagnetChanges(group)"
              >
            </td>
            <td>{{ group.value_type || '-' }}</td>
            <td>{{ getMagnetBindingsText(group.bindings || []) }}</td>
          </tr>
        </tbody>
      </table>
      <span
        v-for="(left, index) in resizeLineLefts"
        :key="`magnet-col-line-${index}`"
        class="table-col-resize-line"
        :style="{ left: `${left}px` }"
        @pointerdown="startColumnResize(index, $event)"
      ></span>
    </div>

    <p v-if="!collapsed && magnetConflicts.length" class="error-text">{{ t('appConfigCenter.magnetConflictsHint') }}</p>
  </article>
</template>
