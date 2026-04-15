<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const columnWidths = ref([260, 320, 120, 320])
const totalTableWidth = computed(() => columnWidths.value.reduce((sum, width) => sum + Number(width || 0), 0))
let stopColumnResize = null

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

onBeforeUnmount(() => {
  if (stopColumnResize) {
    stopColumnResize()
  }
})

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
    <div v-else class="table-wrap resizable-table-wrap">
      <table class="config-table compact config-table-resizable" :style="{ width: `${totalTableWidth}px` }">
        <colgroup>
          <col v-for="(width, index) in columnWidths" :key="`magnet-col-${index}`" :style="{ width: `${width}px` }">
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('appConfigCenter.colPath') }}<span class="table-col-resize-handle" @pointerdown="startColumnResize(0, $event)"></span></th>
            <th>{{ t('appConfigCenter.colCurrent') }}<span class="table-col-resize-handle" @pointerdown="startColumnResize(1, $event)"></span></th>
            <th>{{ t('appConfigCenter.colType') }}<span class="table-col-resize-handle" @pointerdown="startColumnResize(2, $event)"></span></th>
            <th>{{ t('appConfigCenter.magnetBindings') }}</th>
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
    </div>

    <p v-if="!collapsed && magnetConflicts.length" class="error-text">{{ t('appConfigCenter.magnetConflictsHint') }}</p>
  </article>
</template>
