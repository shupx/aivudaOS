<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  osRows: { type: Array, default: () => [] },
  getCellValue: { type: Function, required: true },
  getCellError: { type: Function, required: true },
  displayValue: { type: Function, required: true },
  onEnumChange: { type: Function, required: true },
  onTextChange: { type: Function, required: true },
  valueToInlineText: { type: Function, required: true },
})
</script>

<template>
  <article class="actions-panel">
    <header class="log-header">
      <h3>{{ t('appConfigCenter.osTitle') }}</h3>
    </header>

    <div v-if="!osRows.length" class="empty-box">{{ t('appConfigCenter.osEmpty') }}</div>
    <div v-else class="table-wrap">
      <table class="config-table compact">
        <thead>
          <tr>
            <th>{{ t('appConfigCenter.colPath') }}</th>
            <th>{{ t('appConfigCenter.colCurrent') }}</th>
            <th>{{ t('appConfigCenter.colType') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in osRows" :key="`os:${row.path}`">
            <td class="mono-cell">{{ row.path }}</td>
            <td>
              <div class="config-edit-cell">
                <select
                  v-if="Array.isArray(row.enumValues) && row.enumValues.length"
                  class="select-input"
                  :value="row.enumValues.findIndex((item) => JSON.stringify(item) === JSON.stringify(getCellValue(row)))"
                  @change="onEnumChange(row, $event?.target?.value)"
                >
                  <option v-for="(item, idx) in row.enumValues" :key="idx" :value="idx">
                    {{ valueToInlineText(item) }}
                  </option>
                </select>
                <input
                  v-else
                  class="input"
                  :value="displayValue(row)"
                  @change="onTextChange(row, $event?.target?.value || '')"
                >
                <p v-if="getCellError(row)" class="error-text">{{ t('appConfigCenter.invalidValue') }}: {{ getCellError(row) }}</p>
              </div>
            </td>
            <td>{{ row.type || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
