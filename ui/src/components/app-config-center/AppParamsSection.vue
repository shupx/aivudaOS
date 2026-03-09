<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  rows: { type: Array, default: () => [] },
  getCellValue: { type: Function, required: true },
  getCellError: { type: Function, required: true },
  displayValue: { type: Function, required: true },
  getDefaultText: { type: Function, required: true },
  getRangeText: { type: Function, required: true },
  getDescriptionText: { type: Function, required: true },
  getRowThemeClass: { type: Function, required: true },
  onBooleanChange: { type: Function, required: true },
  onEnumChange: { type: Function, required: true },
  onTextChange: { type: Function, required: true },
  valueToInlineText: { type: Function, required: true },
})
</script>

<template>
  <article class="actions-panel">
    <header class="log-header">
      <h3>{{ t('appConfigCenter.tableTitle') }}</h3>
    </header>

    <div v-if="!rows.length" class="empty-box">{{ t('appConfigCenter.empty') }}</div>

    <div v-else class="table-wrap">
      <table class="config-table">
        <thead>
          <tr>
            <th>{{ t('appConfigCenter.colPath') }}</th>
            <th>{{ t('appConfigCenter.colCurrent') }}</th>
            <th>{{ t('appConfigCenter.colDefault') }}</th>
            <th>{{ t('appConfigCenter.colType') }}</th>
            <th>{{ t('appConfigCenter.colRange') }}</th>
            <th>{{ t('appConfigCenter.colDesc') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, index) in rows" :key="`${row.appId}:${row.path}`">
            <tr
              v-if="index === 0 || rows[index - 1]?.appId !== row.appId"
              class="config-app-title-row"
              :class="getRowThemeClass(row.appId)"
            >
              <td colspan="6">
                {{ row.appName }} ({{ row.appId }} @ {{ row.appVersion || '-' }})
              </td>
            </tr>

            <tr :class="getRowThemeClass(row.appId)">
              <td class="mono-cell">{{ row.path }}</td>
              <td>
                <div class="config-edit-cell">
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
                    v-else-if="Array.isArray(row.enumValues) && row.enumValues.length"
                    class="select-input"
                    :disabled="row.readonly"
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
                    :disabled="row.readonly"
                    :value="displayValue(row)"
                    @change="onTextChange(row, $event?.target?.value || '')"
                  >

                  <p v-if="row.readonly" class="muted">{{ t('appConfigCenter.readonlyInMagnetZone') }}</p>
                  <p v-if="getCellError(row)" class="error-text">{{ t('appConfigCenter.invalidValue') }}: {{ getCellError(row) }}</p>
                </div>
              </td>
              <td class="mono-cell">{{ getDefaultText(row) }}</td>
              <td>{{ row.type || '-' }}</td>
              <td>{{ getRangeText(row) }}</td>
              <td>{{ getDescriptionText(row) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </article>
</template>
