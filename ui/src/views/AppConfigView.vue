<script setup>
import { useI18n } from 'vue-i18n'
import { useAppConfigPage } from '../composables/useAppConfigPage'

const { t } = useI18n()

const {
  appId,
  loading,
  saving,
  error,
  success,
  versions,
  selectedVersion,
  configVersion,
  schemaText,
  constraints,
  configText,
  loadConfig,
  saveConfig,
  goBack,
} = useAppConfigPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('appConfig.title', { appId }) }}</h2>
      <div class="panel-actions">
        <button class="btn" @click="goBack">{{ t('appConfig.back') }}</button>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="loadConfig">
          {{ loading ? t('common.loadingShort') : t('common.refresh') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="success" class="ok-text">{{ success }}</p>

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfig.editTitle') }}</h3>
      </header>

      <div class="panel-actions wrap">
        <label class="muted">{{ t('appConfig.versionLabel') }}</label>
        <select v-model="selectedVersion" class="select-input">
          <option v-for="version in versions" :key="version" :value="version">
            {{ version }}
          </option>
        </select>
        <span class="muted">{{ t('appConfig.revisionLabel', { version: configVersion }) }}</span>
      </div>

      <div class="field">
        <label>{{ t('appConfig.configLabel') }}</label>
        <textarea v-model="configText" class="text-area"></textarea>
      </div>

      <div class="panel-actions wrap">
        <button class="btn primary" :disabled="saving || loading" @click="saveConfig">
          {{ saving ? t('common.processing') : t('appConfig.save') }}
        </button>
      </div>
    </article>

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfig.schemaTitle') }}</h3>
      </header>
      <pre class="log-output config-schema-output">{{ schemaText }}</pre>
    </article>

    <article class="actions-panel">
      <header class="log-header">
        <h3>{{ t('appConfig.constraintTitle') }}</h3>
      </header>
      <div v-if="!constraints.length" class="muted">{{ t('appConfig.noConstraint') }}</div>
      <ul v-else class="constraint-list">
        <li v-for="(item, index) in constraints" :key="index">
          {{ item.left?.app_id }}.{{ item.left?.path }} = {{ item.right?.app_id }}.{{ item.right?.path }}
        </li>
      </ul>
    </article>
  </section>
</template>
