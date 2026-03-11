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
  username,
  enabled,
  toggleEnabled,
  showPasswordModal,
  closePasswordModal,
  sudoPassword,
  showSudoPassword,
  submitToggle,
  reloginNow,
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
    <p v-if="success" class="ok-text">{{ success }}</p>

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
