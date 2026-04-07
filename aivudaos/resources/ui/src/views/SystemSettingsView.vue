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
  showAptSourcesModal,
  aptSourcesLoading,
  aptSourcesWriting,
  aptSourcesText,
  aptSourcesPath,
  aptSourceLines,
  aptSudoPassword,
  showAptSudoPassword,
  showAptPasswordModal,
  aptPendingAction,
  aptBackups,
  selectedAptBackupId,
  aptUpdateOutput,
  aptEditorTextRef,
  aptEditorHighlightRef,
  openAptSourcesModal,
  closeAptSourcesModal,
  closeAptPasswordModal,
  syncAptEditorScroll,
  loadAptSources,
  requestWriteAptSources,
  requestRestoreAptSources,
  submitAptAction,
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

      <div class="setting-row">
        <span class="setting-row-label">{{ t('systemSettings.aptSourcesAction') }}</span>
        <button class="btn" :disabled="loading || saving" @click="openAptSourcesModal">
          {{ t('systemSettings.aptSourcesButton') }}
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

    <div v-if="showAptSourcesModal" class="modal-overlay">
      <section class="modal-card modal-wide apt-modal">
        <header class="modal-header">
          <h3>{{ t('systemSettings.aptSourcesTitle') }}</h3>
          <button
            class="modal-close-btn"
            type="button"
            :disabled="aptSourcesWriting"
            @click="closeAptSourcesModal"
          >
            ×
          </button>
        </header>

        <p class="muted">{{ aptSourcesPath }}</p>

        <div class="panel-actions wrap">
          <button class="btn" :disabled="aptSourcesLoading || aptSourcesWriting" @click="loadAptSources">
            {{ aptSourcesLoading ? t('common.loadingShort') : t('systemSettings.aptRead') }}
          </button>
          <button class="btn primary" :disabled="aptSourcesLoading || aptSourcesWriting" @click="requestWriteAptSources">
            {{ aptSourcesWriting ? t('common.processing') : t('systemSettings.aptWrite') }}
          </button>
        </div>

        <div class="field">
          <label for="apt-sources-text">{{ t('systemSettings.aptSourcesEditorLabel') }}</label>
          <div class="apt-editor-shell">
            <pre ref="aptEditorHighlightRef" class="apt-editor-highlight"><span
              v-for="line in aptSourceLines"
              :key="line.key"
              :class="line.comment ? 'apt-line-comment' : 'apt-line-normal'"
            >{{ line.text }}
</span></pre>
            <textarea
              id="apt-sources-text"
              ref="aptEditorTextRef"
              v-model="aptSourcesText"
              class="apt-editor-text mono-input"
              :disabled="aptSourcesLoading || aptSourcesWriting"
              spellcheck="false"
              @scroll="syncAptEditorScroll"
            />
          </div>
        </div>

        <div class="field">
          <label for="apt-backup-select">{{ t('systemSettings.aptBackupsLabel') }}</label>
          <div class="inline-row wrap">
            <select
              id="apt-backup-select"
              v-model="selectedAptBackupId"
              class="select-input"
              :disabled="aptSourcesLoading || aptSourcesWriting || !aptBackups.length"
            >
              <option v-if="!aptBackups.length" value="">{{ t('systemSettings.aptBackupsEmpty') }}</option>
              <option
                v-for="item in aptBackups"
                :key="`apt-backup-${item.backup_id}`"
                :value="item.backup_id"
              >
                {{ item.created_at || item.backup_id }}
              </option>
            </select>
            <button
              class="btn danger"
              :disabled="aptSourcesLoading || aptSourcesWriting || !aptBackups.length || !selectedAptBackupId"
              @click="requestRestoreAptSources"
            >
              {{ aptSourcesWriting ? t('common.processing') : t('systemSettings.aptRestore') }}
            </button>
          </div>
        </div>

        <div v-if="aptUpdateOutput" class="field">
          <label>{{ t('systemSettings.aptUpdateOutput') }}</label>
          <pre class="log-output">{{ aptUpdateOutput }}</pre>
        </div>

        <div v-if="showAptPasswordModal" class="modal-overlay modal-overlay-inner" @click.self="closeAptPasswordModal">
          <section class="modal-card">
            <header class="modal-header">
              <h3>{{ t('systemSettings.aptConfirmPasswordTitle') }}</h3>
            </header>

            <p class="muted">
              {{ aptPendingAction === 'restore' ? t('systemSettings.aptConfirmRestoreHint') : t('systemSettings.aptConfirmWriteHint') }}
            </p>

            <div class="field">
              <label for="apt-modal-password-input">{{ t('systemSettings.sudoPassword') }}</label>
              <div class="inline-row">
                <input
                  id="apt-modal-password-input"
                  v-model="aptSudoPassword"
                  class="mono-input"
                  :type="showAptSudoPassword ? 'text' : 'password'"
                  :placeholder="t('systemSettings.sudoPasswordPlaceholder')"
                  :disabled="aptSourcesWriting"
                  autocomplete="current-password"
                  @keydown.enter="submitAptAction"
                >
                <button
                  class="btn"
                  type="button"
                  :disabled="aptSourcesWriting"
                  @click="showAptSudoPassword = !showAptSudoPassword"
                >
                  {{ showAptSudoPassword ? t('systemSettings.hidePassword') : t('systemSettings.showPassword') }}
                </button>
              </div>
            </div>

            <div class="panel-actions">
              <button class="btn" :disabled="aptSourcesWriting" @click="closeAptPasswordModal">
                {{ t('common.cancel') }}
              </button>
              <button class="btn primary" :disabled="aptSourcesWriting || !aptSudoPassword.trim()" @click="submitAptAction">
                {{ aptSourcesWriting ? t('common.processing') : t('systemSettings.confirm') }}
              </button>
            </div>
          </section>
        </div>
      </section>
    </div>
  </section>
</template>
