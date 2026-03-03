<script setup>
import { useUploadInstallModalView } from '../../composables/useUploadInstallModalView'

const props = defineProps({
  visible: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  status: { type: String, default: '' },
  statusDone: { type: Boolean, default: false },
  output: { type: String, default: '' },
  fileName: { type: String, default: '' },
  hint: { type: String, default: '' },
  showFilePicker: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'file-change', 'submit'])

const {
  t,
  logRef,
  onLogScroll,
  shouldShowOutput,
  onFileChange,
  closeByOverlay,
} = useUploadInstallModalView(props, emit)
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="closeByOverlay">
    <section class="modal-card">
      <header class="modal-header">
        <h3>{{ t('apps.uploadModalTitle') }}</h3>
      </header>

      <p v-if="hint" class="muted">{{ hint }}</p>

      <div v-if="showFilePicker" class="field">
        <label>{{ t('apps.packageFile') }}</label>
        <input
          class="file-input"
          type="file"
          accept=".tar.gz,.zip"
          @change="onFileChange"
        >
      </div>
      <p class="muted">{{ fileName || t('apps.noFileSelected') }}</p>

      <p v-if="error" class="error-text">{{ error }}</p>
      <p
        v-if="status"
        :class="statusDone ? 'ok-text' : 'muted'"
      >
        {{ t('common.status') }}：{{ status }}
      </p>
      <pre
        v-if="shouldShowOutput"
        ref="logRef"
        class="log-output small"
        @scroll="onLogScroll"
      ></pre>

      <footer class="panel-actions">
        <button class="btn" :disabled="busy" @click="$emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn primary" :disabled="busy || !fileName" @click="$emit('submit')">
          {{ busy ? t('apps.uploading') : t('apps.uploadAndInstall') }}
        </button>
      </footer>
    </section>
  </div>
</template>
