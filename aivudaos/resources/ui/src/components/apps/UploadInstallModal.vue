<script setup>
import { useUploadInstallModalView } from '../../composables/useUploadInstallModalView'
import { NModal, NCard, NButton, NInput, NText, NAlert } from 'naive-ui'
import { useI18n } from 'vue-i18n'

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
  onLogScroll,
  onFileChange,
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

        <div v-if="showFilePicker" style="display: flex; flex-direction: column; gap: 8px;">
          <NText>{{ t('apps.packageFile') }}</NText>
          <input
            type="file"
            accept=".tar.gz,.zip"
            @change="onFileChange"
            style="border: 1px solid #dbe2ea; border-radius: 10px; padding: 8px; width: 100%; box-sizing: border-box; background: #fff;"
          >
        </div>
        <NText depth="3" style="font-size: 13px;">{{ fileName || t('apps.noFileSelected') }}</NText>

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
