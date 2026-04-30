<script setup>
import { useI18n } from 'vue-i18n'
import SwitchToggle from '../components/apps/SwitchToggle.vue'
import { useSystemSettingsPage } from '../composables/useSystemSettingsPage'
import {
  NCard, NSpace, NButton, NText, NAlert, NIcon, NGrid, NGi, NTag, NModal, NInput, NCheckbox, NSelect, NDataTable
} from 'naive-ui'
import { RefreshCw, Download, Play, Square, Trash2, RotateCcw } from 'lucide-vue-next'

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
  serviceInstalled,
  serviceRunning,
  serviceAutostartEnabled,
  serviceActionPending,
  caddyLocalCaDownloadUrl,
  caddyLocalCaHintVisible,
  downloadCaddyLocalCa,
  toggleEnabled,
  toggleServiceAutostart,
  triggerServiceAction,
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
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <NText style="font-size: 20px; font-weight: 600;">{{ t('systemSettings.title') }}</NText>
      <NButton secondary size="small" :loading="loading || saving" @click="load">
        <template #icon><NIcon><RefreshCw /></NIcon></template>
        {{ t('common.refresh') }}
      </NButton>
    </div>

    <NAlert v-if="error" type="error" style="margin-bottom: 24px;">{{ error }}</NAlert>
    <NAlert v-if="success" type="success" style="margin-bottom: 24px;">
      {{ success }}
      <template v-if="successLinks.length">
        <span
          v-for="(link, index) in successLinks"
          :key="`success-link-${link.url}`"
        >
          <span>{{ index === 0 ? ' ' : ' / ' }}</span>
          <a :href="link.url" target="_blank" rel="noopener noreferrer" style="color: #10b981; text-decoration: underline;">{{ link.label }}</a>
        </span>
      </template>
    </NAlert>

    <NGrid x-gap="24" y-gap="24" cols="1" responsive="screen" style="margin-bottom: 24px;">
      <NGi>
        <NCard :title="t('systemSettings.currentUser')">
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.currentUser') }}</NText>
              <NText depth="3" class="setting-row-content">{{ username || '-' }}</NText>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.passwordlessSudo') }}</NText>
              <SwitchToggle
                :model-value="enabled"
                :disabled="loading || saving"
                @update:model-value="toggleEnabled"
              />
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.reloginAction') }}</NText>
              <NButton type="error" size="small" :loading="reloginPending" :disabled="loading || saving" @click="reloginNow">
                {{ t('systemSettings.reloginNow') }}
              </NButton>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.aptSourcesAction') }}</NText>
              <NButton size="small" :disabled="loading || saving" @click="openAptSourcesModal">
                {{ t('systemSettings.aptSourcesButton') }}
              </NButton>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.caddyLocalCaLabel') }}</NText>
              <NButton size="small" tag="a" :href="caddyLocalCaDownloadUrl" :disabled="loading || saving" @click.prevent="downloadCaddyLocalCa">
                <template #icon><NIcon><Download /></NIcon></template>
                {{ t('systemSettings.caddyLocalCaDownloadLink') }}
              </NButton>
            </div>
            <NAlert v-if="caddyLocalCaHintVisible" type="info">
              {{ t('systemSettings.caddyLocalCaHintPrefix') }}
              <a :href="t('systemSettings.caddyLocalCaChromeUrl')" target="_blank" rel="noopener noreferrer" style="color: #3b82f6;">
                {{ t('systemSettings.caddyLocalCaChromeUrl') }}
              </a>
              {{ t('systemSettings.caddyLocalCaHintMiddle') }}
              <strong>{{ t('systemSettings.caddyLocalCaTrustedCertificates') }}</strong>
              {{ t('systemSettings.caddyLocalCaHintImport') }}
              <strong>{{ t('systemSettings.caddyLocalCaImportAction') }}</strong>
              {{ t('systemSettings.caddyLocalCaHintSuffix') }}
            </NAlert>
          </div>
        </NCard>
      </NGi>

      <NGi>
        <NCard :title="t('systemSettings.aivudaosServiceTitle')">
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div class="setting-actions-wrap">
              <NButton
                type="error" size="small"
                :loading="serviceActionPending === 'stop'"
                :disabled="loading || saving || !serviceInstalled || !serviceRunning || Boolean(serviceActionPending)"
                @click="triggerServiceAction('stop')"
              >
                <template #icon><NIcon><Square /></NIcon></template>
                {{ t('systemSettings.serviceStopButton') }}
              </NButton>
              <NButton
                type="error" size="small"
                :loading="serviceActionPending === 'uninstall'"
                :disabled="loading || saving || !serviceInstalled || Boolean(serviceActionPending)"
                @click="triggerServiceAction('uninstall')"
              >
                <template #icon><NIcon><Trash2 /></NIcon></template>
                {{ t('systemSettings.serviceUninstallButton') }}
              </NButton>
              <NButton
                size="small"
                :loading="serviceActionPending === 'restart'"
                :disabled="loading || saving || !serviceInstalled || Boolean(serviceActionPending)"
                @click="triggerServiceAction('restart')"
              >
                <template #icon><NIcon><RotateCcw /></NIcon></template>
                {{ t('systemSettings.serviceRestartButton') }}
              </NButton>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.serviceInstalledLabel') }}</NText>
              <NTag :type="serviceInstalled ? 'success' : 'default'">
                {{ serviceInstalled ? t('systemSettings.statusEnabled') : t('systemSettings.statusDisabled') }}
              </NTag>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.serviceRunningLabel') }}</NText>
              <NTag :type="serviceRunning ? 'success' : 'error'">
                {{ serviceRunning ? t('appCard.running') : t('appCard.stopped') }}
              </NTag>
            </div>
            <div class="setting-row setting-row-wrap">
              <NText class="setting-row-label-fixed">{{ t('systemSettings.serviceAutostartLabel') }}</NText>
              <SwitchToggle
                :model-value="serviceAutostartEnabled"
                :disabled="loading || saving || !serviceInstalled || Boolean(serviceActionPending)"
                @update:model-value="toggleServiceAutostart"
              />
            </div>
          </div>
        </NCard>
      </NGi>

      <NGi>
        <NCard :title="t('systemSettings.osParamsTitle')">
          <div v-if="!osRows.length">
             <NText depth="3">{{ t('systemSettings.osParamsEmpty') }}</NText>
          </div>
          <div v-else class="table-wrap">
            <table class="config-table compact" style="width: 100%;">
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
                      <NCheckbox
                        v-if="row.type === 'boolean'"
                        :checked="Boolean(getOsCellValue(row))"
                        @update:checked="(val) => onOsBooleanChange(row, val)"
                      >
                        {{ Boolean(getOsCellValue(row)) ? 'true' : 'false' }}
                      </NCheckbox>
                      <NSelect
                        v-else-if="getOsEnumOptions(row).length"
                        size="small"
                        :value="String(getOsCellValue(row) ?? '')"
                        :options="getOsEnumOptions(row).map(o => ({ label: o.value, value: o.value, disabled: o.disabled }))"
                        @update:value="(val) => onOsEnumChange(row, val)"
                      />
                      <NInput
                        v-else
                        size="small"
                        :value="displayOsValue(row)"
                        @update:value="(val) => onOsTextChange(row, val)"
                      />
                      <p v-if="getOsCellError(row)" class="error-text" style="margin-top: 4px; font-size: 12px;">
                        {{ t('systemSettings.osInvalidValue') }}: {{ getOsCellError(row) }}
                      </p>
                    </div>
                  </td>
                  <td><NTag size="small">{{ row.type || '-' }}</NTag></td>
                </tr>
              </tbody>
            </table>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NModal v-model:show="showPasswordModal" preset="card" style="width: 400px;" :title="t('systemSettings.confirmPasswordTitle')" @after-leave="closePasswordModal">
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <NText depth="3">{{ enabled ? t('systemSettings.confirmDisableHint') : t('systemSettings.confirmEnableHint') }}</NText>
        <NInput
          v-model:value="sudoPassword"
          type="password"
          show-password-on="click"
          :placeholder="t('systemSettings.sudoPasswordPlaceholder')"
          :disabled="saving"
          @keydown.enter="submitToggle"
        />
        <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px;">
          <NButton @click="closePasswordModal" :disabled="saving">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="saving" :disabled="!sudoPassword.trim()" @click="submitToggle">{{ t('systemSettings.confirm') }}</NButton>
        </div>
      </div>
    </NModal>

    <!-- Keeping AptSourcesModal partially custom because it uses complex apt editors not easily replaced by standard inputs -->
    <div v-if="showAptSourcesModal" class="modal-overlay" style="z-index: 100;">
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
          <NButton :loading="aptSourcesLoading" :disabled="aptSourcesWriting" @click="loadAptSources">
            {{ t('systemSettings.aptRead') }}
          </NButton>
          <NButton type="primary" :loading="aptSourcesWriting" :disabled="aptSourcesLoading" @click="requestWriteAptSources">
            {{ t('systemSettings.aptWrite') }}
          </NButton>
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

        <NModal v-model:show="showAptPasswordModal" preset="card" style="width: 400px;" :title="t('systemSettings.aptConfirmPasswordTitle')" @after-leave="closeAptPasswordModal">
          <div style="display: flex; flex-direction: column; gap: 16px;">
             <NText depth="3">{{ aptPendingAction === 'restore' ? t('systemSettings.aptConfirmRestoreHint') : t('systemSettings.aptConfirmWriteHint') }}</NText>
             <NInput
               v-model:value="aptSudoPassword"
               type="password"
               show-password-on="click"
               :placeholder="t('systemSettings.sudoPasswordPlaceholder')"
               :disabled="aptSourcesWriting"
               @keydown.enter="submitAptAction"
             />
             <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px;">
               <NButton @click="closeAptPasswordModal" :disabled="aptSourcesWriting">{{ t('common.cancel') }}</NButton>
               <NButton type="primary" :loading="aptSourcesWriting" :disabled="!aptSudoPassword.trim()" @click="submitAptAction">{{ t('systemSettings.confirm') }}</NButton>
             </div>
          </div>
        </NModal>
      </section>
    </div>
  </section>
</template>
