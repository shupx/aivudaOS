<script setup>
import { useI18n } from 'vue-i18n'
import SwitchToggle from '../components/apps/SwitchToggle.vue'
import { useSystemSettingsPage } from '../composables/useSystemSettingsPage'

const { t } = useI18n()
const {
  loading,
  saving,
  reloginPending,
  error,
  success,
  successLinks,
  username,
  enabled,
  toggleEnabled,
  showPasswordModal,
  closePasswordModal,
  sudoPassword,
  showSudoPassword,
  submitToggle,
  reloginNow,
  osRows,
  getOsCellValue,
  getOsCellError,
  getOsEnumOptions,
  displayOsValue,
  onOsBooleanChange,
  onOsEnumChange,
  onOsTextChange,
  load,
} = useSystemSettingsPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('systemSettings.title') }}</h2>
      <div class="panel-actions wrap">
        <button class="btn btn-stable-refresh" :disabled="loading || saving" @click="load">
          {{ loading ? t('common.loadingShort') : t('common.refresh') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="success" class="ok-text">
      <span>{{ success }}</span>
      <template v-if="successLinks.length">
        <span
          v-for="(link, index) in successLinks"
          :key="`success-link-${link.url}`"
        >
          <span>{{ index === 0 ? ' ' : ' / ' }}</span>
          <a :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.label }}</a>
        </span>
      </template>
    </p>

    <article class="actions-panel">
      <div class="setting-row">
        <span class="setting-row-label">{{ t('systemSettings.currentUser') }}</span>
        <span class="muted">{{ username || '-' }}</span>
      </div>

      <div class="setting-row">
        <span class="setting-row-label">{{ t('systemSettings.passwordlessSudo') }}</span>
        <SwitchToggle
          :model-value="enabled"
          :disabled="loading || saving"
          @update:model-value="toggleEnabled"
        />
      </div>

      <div class="setting-row">
        <span class="setting-row-label">{{ t('systemSettings.reloginAction') }}</span>
        <button class="btn danger" :disabled="loading || saving || reloginPending" @click="reloginNow">
          {{ reloginPending ? t('common.processing') : t('systemSettings.reloginNow') }}
        </button>
      </div>
    </article>

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('systemSettings.osParamsTitle') }}</h3>
      </header>

      <div v-if="!osRows.length" class="empty-box">{{ t('systemSettings.osParamsEmpty') }}</div>
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
                  <label v-if="row.type === 'boolean'" class="check-item">
                    <input
                      :checked="Boolean(getOsCellValue(row))"
                      type="checkbox"
                      @change="onOsBooleanChange(row, $event?.target?.checked)"
                    >
                    {{ Boolean(getOsCellValue(row)) ? 'true' : 'false' }}
                  </label>
                  <select
                    v-else-if="getOsEnumOptions(row).length"
                    class="select-input"
                    :value="String(getOsCellValue(row) ?? '')"
                    @change="onOsEnumChange(row, $event?.target?.value || '')"
                  >
                    <option
                      v-for="item in getOsEnumOptions(row)"
                      :key="`os-enum-${row.path}-${item.value}`"
                      :value="item.value"
                      :disabled="item.disabled"
                    >
                      {{ item.value }}
                    </option>
                  </select>
                  <input
                    v-else
                    class="input"
                    :value="displayOsValue(row)"
                    @change="onOsTextChange(row, $event?.target?.value || '')"
                  >
                  <p v-if="getOsCellError(row)" class="error-text">
                    {{ t('systemSettings.osInvalidValue') }}: {{ getOsCellError(row) }}
                  </p>
                </div>
              </td>
              <td>{{ row.type || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <!-- Password Modal -->
    <div v-if="showPasswordModal" class="modal-overlay" @click.self="closePasswordModal">
      <section class="modal-card">
        <header class="modal-header">
          <h3>{{ t('systemSettings.confirmPasswordTitle') }}</h3>
        </header>

        <p class="muted">
          {{ enabled ? t('systemSettings.confirmDisableHint') : t('systemSettings.confirmEnableHint') }}
        </p>

        <div class="field">
          <label for="modal-password-input">{{ t('systemSettings.sudoPassword') }}</label>
          <div class="inline-row">
            <input
              id="modal-password-input"
              v-model="sudoPassword"
              class="mono-input"
              :type="showSudoPassword ? 'text' : 'password'"
              :placeholder="t('systemSettings.sudoPasswordPlaceholder')"
              :disabled="saving"
              autocomplete="current-password"
              @keydown.enter="submitToggle"
            >
            <button
              class="btn"
              type="button"
              :disabled="saving"
              @click="showSudoPassword = !showSudoPassword"
            >
              {{ showSudoPassword ? t('systemSettings.hidePassword') : t('systemSettings.showPassword') }}
            </button>
          </div>
        </div>

        <div class="panel-actions">
          <button
            class="btn"
            :disabled="saving"
            @click="closePasswordModal"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            class="btn primary"
            :disabled="saving || !sudoPassword.trim()"
            @click="submitToggle"
          >
            {{ saving ? t('common.processing') : t('systemSettings.confirm') }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
