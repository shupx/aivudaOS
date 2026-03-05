<script setup>
import { useI18n } from 'vue-i18n'
import { useAppConfigCenterPage } from '../composables/useAppConfigCenterPage'

const { t } = useI18n()

const {
  loading,
  saving,
  error,
  success,
  appOptions,
  selectedAppId,
  rows,
  hasChanges,
  showConfirmModal,
  pendingChanges,
  loadAllConfigs,
  openSaveConfirm,
  closeSaveConfirm,
  confirmSave,
  goBackApps,
  getCellValue,
  getCellError,
  displayValue,
  getDefaultText,
  getRangeText,
  getDescriptionText,
  getRowThemeClass,
  onBooleanChange,
  onEnumChange,
  onTextChange,
  valueToInlineText,
} = useAppConfigCenterPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('appConfigCenter.title') }}</h2>
      <div class="panel-actions wrap">
        <button class="btn" @click="goBackApps">{{ t('appConfigCenter.backToApps') }}</button>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="loadAllConfigs">
          {{ loading ? t('common.loadingShort') : t('common.refresh') }}
        </button>
        <button class="btn primary" :disabled="saving || loading || !hasChanges" @click="openSaveConfirm">
          {{ saving ? t('common.processing') : t('appConfigCenter.saveAll') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="success" class="ok-text">{{ success }}</p>

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfigCenter.filterTitle') }}</h3>
      </header>
      <div class="panel-actions wrap">
        <label class="muted" for="config-center-app-select">{{ t('appConfigCenter.filterApp') }}</label>
        <select id="config-center-app-select" v-model="selectedAppId" class="select-input">
          <option value="">{{ t('appConfigCenter.filterAll') }}</option>
          <option v-for="item in appOptions" :key="item.appId" :value="item.appId">
            {{ item.name }} ({{ item.appId }} @ {{ item.version }})
          </option>
        </select>
      </div>
    </article>

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
                      type="checkbox"
                      @change="onBooleanChange(row, $event?.target?.checked)"
                    >
                    {{ Boolean(getCellValue(row)) ? 'true' : 'false' }}
                  </label>

                  <select
                    v-else-if="Array.isArray(row.enumValues) && row.enumValues.length"
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

    <div v-if="showConfirmModal" class="modal-overlay" @click.self="saving ? null : closeSaveConfirm()">
      <section class="modal-card modal-wide">
        <header class="modal-header">
          <h3>{{ t('appConfigCenter.confirmTitle') }}</h3>
        </header>

        <p class="muted">{{ t('appConfigCenter.confirmHint') }}</p>

        <div class="table-wrap">
          <table class="config-table compact">
            <thead>
              <tr>
                <th>{{ t('appConfigCenter.colApp') }}</th>
                <th>{{ t('appConfigCenter.colPath') }}</th>
                <th>{{ t('appConfigCenter.colBefore') }}</th>
                <th>{{ t('appConfigCenter.colAfter') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in pendingChanges" :key="`${item.appId}:${item.path}`">
                <td>{{ item.appName }} ({{ item.appId }})</td>
                <td class="mono-cell">{{ item.path }}</td>
                <td class="mono-cell">{{ valueToInlineText(item.before) }}</td>
                <td class="mono-cell">{{ valueToInlineText(item.after) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="panel-actions">
          <button class="btn" :disabled="saving" @click="closeSaveConfirm">{{ t('common.cancel') }}</button>
          <button class="btn primary" :disabled="saving" @click="confirmSave">
            {{ saving ? t('common.processing') : t('appConfigCenter.confirmSave') }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
