<script setup>
import { useUploadInstallModalView } from '../../composables/useUploadInstallModalView'
import { NModal, NCard, NButton, NInput, NText, NAlert } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { UploadCloud, FileArchive } from 'lucide-vue-next'

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
  cancelBusy: { type: Boolean, default: false },
  interactiveInput: { type: String, default: '' },
  interactiveReady: { type: Boolean, default: false },
  interactiveMaskInput: { type: Boolean, default: true },
})

const emit = defineEmits([
  'close',
  'file-change',
  'submit',
  'interactive-input',
  'interactive-submit',
  'interactive-mask-change',
  'cancel-operation',
])

const { t } = useI18n()

const {
  shouldShowOutput,
  logRef,
  isDragOver,
  onLogScroll,
  onFileChange,
  onDragEnter,
  onDragOver,
  onDragLeave,
  onDrop,
  closeByOverlay,
  onInteractiveInput,
  onInteractiveKeydown,
  onInteractiveMaskChange,
} = useUploadInstallModalView(props, emit)
</script>

<template>
  <NModal :show="visible" @mask-click="closeByOverlay" :mask-closable="!busy">
    <NCard
      class="upload-install-modal-card"
      style="width: min(720px, 95vw);"
      :content-style="{ display: 'flex', flexDirection: 'column', gap: '16px', minHeight: '0' }"
      :title="t('apps.uploadModalTitle')"
      :bordered="false"
      size="huge"
      role="dialog"
      aria-modal="true"
    >
      <div class="upload-install-modal-body" style="display: flex; flex-direction: column; gap: 16px;">
        <NText v-if="hint" depth="3">{{ hint }}</NText>

        <div v-if="showFilePicker && !fileName" style="display: flex; flex-direction: column; gap: 8px;">
          <NText>{{ t('apps.packageFile') }}</NText>
          <label
            class="upload-dropzone"
            :class="{ 'upload-dropzone--active': isDragOver }"
            @dragenter="onDragEnter"
            @dragover="onDragOver"
            @dragleave="onDragLeave"
            @drop="onDrop"
          >
            <input
              type="file"
              accept=".tar.gz,.zip"
              class="upload-dropzone-input"
              @change="onFileChange"
            >
            <div class="upload-dropzone-icon-wrap">
              <UploadCloud class="upload-dropzone-icon" />
            </div>
            <span class="upload-dropzone-title">
              {{ t('apps.packageDropzoneTitle') }}
            </span>
            <span class="upload-dropzone-subtitle">
              {{ t('apps.packageDropzoneHint') }}
            </span>
            <span class="upload-dropzone-badge">
              {{ t('apps.packageDropzoneButton') }}
            </span>
          </label>
        </div>
        <div class="upload-selected-file" :class="{ 'upload-selected-file--empty': !fileName }">
          <FileArchive class="upload-selected-file-icon" />
          <NText depth="3" style="font-size: 13px;">{{ fileName || t('apps.noFileSelected') }}</NText>
        </div>

        <NAlert v-if="error" type="error">{{ error }}</NAlert>
        <NText v-if="status" :type="statusDone ? 'success' : 'default'">
          {{ t('common.status') }}：{{ status }}
        </NText>

        <pre
          v-if="shouldShowOutput"
          ref="logRef"
          class="log-output modal-log-output"
          @scroll="onLogScroll"
        ></pre>

        <div v-if="busy" style="display: flex; flex-direction: column; gap: 8px;">
          <NText>{{ t('apps.interactiveInputLabel') }}</NText>
          <div style="display: flex; gap: 8px;">
              <NInput
                :type="interactiveMaskInput ? 'password' : 'text'"
                :placeholder="t('apps.interactiveInputPlaceholder')"
                :value="interactiveInput"
                @update:value="(val) => onInteractiveInput({ target: { value: val } })"
                @keydown="onInteractiveKeydown"
                style="flex: 1;"
              />
            <NButton @click="onInteractiveMaskChange(!interactiveMaskInput)">
              {{ interactiveMaskInput ? t('apps.interactiveShowInput') : t('apps.interactiveHideInput') }}
            </NButton>
            <NButton type="primary" @click="emit('interactive-submit')">
              {{ t('apps.interactiveSend') }}
            </NButton>
          </div>
        </div>

        <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px;">
          <NButton :disabled="busy" @click="emit('close')">{{ t('common.cancel') }}</NButton>
          <NButton v-if="busy" type="error" :loading="cancelBusy" @click="emit('cancel-operation')">
            {{ t('apps.exitInstall') }}
          </NButton>
          <NButton type="primary" :disabled="busy || !fileName" :loading="busy" @click="emit('submit')">
            {{ t('apps.uploadAndInstall') }}
          </NButton>
        </div>
      </div>
    </NCard>
  </NModal>
</template>

<style scoped>
.upload-dropzone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 112px;
  padding: 14px 16px;
  border: 2px dashed #cbd5e1;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.upload-dropzone:hover,
.upload-dropzone--active {
  border-color: #10b981;
  background: linear-gradient(180deg, #f0fdf4 0%, #ecfdf5 100%);
  box-shadow: 0 14px 32px rgba(16, 185, 129, 0.12);
  transform: translateY(-1px);
}

.upload-dropzone-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.upload-dropzone-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: #ffffff;
  color: #64748b;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
  transition: color 0.2s ease, background 0.2s ease;
}

.upload-dropzone:hover .upload-dropzone-icon-wrap,
.upload-dropzone--active .upload-dropzone-icon-wrap {
  background: #ecfdf5;
  color: #059669;
}

.upload-dropzone-icon {
  width: 18px;
  height: 18px;
}

.upload-dropzone-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
}

.upload-dropzone-subtitle {
  max-width: 400px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.upload-dropzone-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.upload-selected-file {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
  color: #334155;
}

.upload-selected-file--empty {
  color: #64748b;
}

.upload-selected-file-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
}

@media (max-width: 640px) {
  .upload-dropzone {
    min-height: 96px;
    padding: 12px 14px;
  }
}
</style>
