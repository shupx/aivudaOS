<script setup>
import { useI18n } from 'vue-i18n'
import { useAppConfigCenterPage } from '../composables/useAppConfigCenterPage'
import MagnetConfigSection from '../components/app-config-center/MagnetConfigSection.vue'
import OsConfigSection from '../components/app-config-center/OsConfigSection.vue'
import AppParamsSection from '../components/app-config-center/AppParamsSection.vue'

const { t } = useI18n()

const {
  loading,
  error,
  success,
  appOptions,
  selectedAppId,
  rows,
  systemRows,
  osRows,
  magnets,
  magnetConflicts,
  magnetSaving,
  loadAllConfigs,
  goBackApps,
  getCellValue,
  getCellError,
  displayValue,
  getDefaultText,
  getRangeText,
  getDescriptionText,
  getRowThemeClass,
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
  onBooleanChange,
  onEnumChange,
  onSystemEnumChange,
  onTextChange,
  openSystemAddModal,
  closeSystemAddModal,
  addSystemParam,
  confirmRemoveSystemParam,
  onMagnetBooleanChange,
  onMagnetTextChange,
  saveMagnetChanges,
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

    <MagnetConfigSection
      :magnets="magnets"
      :magnet-conflicts="magnetConflicts"
      :get-magnet-value="getMagnetValue"
      :get-magnet-display-value="getMagnetDisplayValue"
      :on-magnet-boolean-change="onMagnetBooleanChange"
      :on-magnet-text-change="onMagnetTextChange"
      :save-magnet-changes="saveMagnetChanges"
      :value-to-inline-text="valueToInlineText"
    />

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfigCenter.systemTitle') }}</h3>
      </header>

      <div class="panel-actions wrap" style="margin-bottom: 10px;">
        <button class="btn" @click="openSystemAddModal">{{ t('appConfigCenter.systemAdd') }}</button>
      </div>

      <div v-if="!systemRows.length" class="empty-box">{{ t('appConfigCenter.systemEmpty') }}</div>
      <div v-else class="table-wrap">
        <table class="config-table compact">
          <thead>
            <tr>
              <th>{{ t('appConfigCenter.colPath') }}</th>
              <th>{{ t('appConfigCenter.colCurrent') }}</th>
              <th>{{ t('appConfigCenter.colType') }}</th>
              <th>{{ t('appConfigCenter.colRange') }}</th>
              <th>{{ t('appConfigCenter.colDesc') }}</th>
              <th>{{ t('appConfigCenter.colAction') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in systemRows" :key="`sys:${row.path}`">
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
                  <input
                    v-else
                    class="input"
                    :type="getSystemInputType(row)"
                    :disabled="row.readonly"
                    :placeholder="getSystemValuePlaceholder(row)"
                    :value="displayValue(row)"
                    @change="onTextChange(row, $event?.target?.value || '')"
                  >

                  <p v-if="row.readonly" class="muted">{{ t('appConfigCenter.readonlyInMagnetZone') }}</p>
                  <p v-if="getCellError(row)" class="error-text">{{ t('appConfigCenter.invalidValue') }}: {{ getCellError(row) }}</p>
                </div>
              </td>
              <td>{{ row.type || '-' }}</td>
              <td>{{ row.rangeText || '-' }}</td>
              <td>{{ row.description || '-' }}</td>
              <td>
                <button class="btn" :disabled="row.readonly" @click="confirmRemoveSystemParam(row)">
                  {{ t('appConfigCenter.systemDelete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
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

    <OsConfigSection
      :os-rows="osRows"
      :get-cell-value="getCellValue"
      :get-cell-error="getCellError"
      :display-value="displayValue"
      :on-enum-change="onEnumChange"
      :on-text-change="onTextChange"
      :value-to-inline-text="valueToInlineText"
    />

    <AppParamsSection
      :rows="rows"
      :get-cell-value="getCellValue"
      :get-cell-error="getCellError"
      :display-value="displayValue"
      :get-default-text="getDefaultText"
      :get-range-text="getRangeText"
      :get-description-text="getDescriptionText"
      :get-row-theme-class="getRowThemeClass"
      :on-boolean-change="onBooleanChange"
      :on-enum-change="onEnumChange"
      :on-text-change="onTextChange"
      :value-to-inline-text="valueToInlineText"
    />

  </section>
</template>
