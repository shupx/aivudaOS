<script setup>
import { useI18n } from 'vue-i18n'
import UploadInstallModal from '../components/apps/UploadInstallModal.vue'
import { useOnlineStoreDetailPage } from '../composables/useOnlineStoreDetailPage'
import { NCard, NSpace, NButton, NText, NAlert, NIcon, NEmpty, NGrid, NGi, NProgress } from 'naive-ui'
import { RefreshCw, ArrowLeft, Download, ArrowDownToLine } from 'lucide-vue-next'

const { t } = useI18n()

const {
  appId,
  loading,
  error,
  actionError,
  actionMessage,
  appInfo,
  versions,
  actingByVersion,
  localDownloadingByVersion,
  getDownloadProgress,
  load,
  downloadAndInstallVersion,
  downloadPackageToLocal,
  backToStore,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadStatus,
  uploadStatusDone,
  uploadOutput,
  uploadFileName,
  uploadHint,
  uploadShowFilePicker,
  uploadInteractiveInput,
  uploadInteractiveReady,
  uploadInteractiveMaskInput,
  uploadCancelBusy,
  closeUploadModal,
  setInteractiveInput,
  setInteractiveMaskInput,
  onUploadFileChange,
  submitUpload,
  cancelCurrentUpload,
  submitInteractiveInput,
} = useOnlineStoreDetailPage()
</script>

<template>
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <NSpace align="center">
        <NButton quaternary circle @click="backToStore" :title="t('store.backToStore')">
           <template #icon><NIcon><ArrowLeft /></NIcon></template>
        </NButton>
        <NText style="font-size: 20px; font-weight: 600;">{{ t('store.detailTitle') }}</NText>
      </NSpace>
      <NButton secondary size="small" :loading="loading" @click="load">
        <template #icon><NIcon><RefreshCw /></NIcon></template>
        {{ t('common.refresh') }}
      </NButton>
    </div>

    <NCard style="margin-bottom: 24px;">
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <NText style="font-size: 18px; font-weight: 600;">{{ appInfo?.name || appId }}</NText>
        <NText depth="3" style="font-size: 13px;">app_id: {{ appId }}</NText>
        <NText style="font-size: 14px; margin-top: 8px;">{{ appInfo?.description || t('store.noDescription') }}</NText>
      </div>
    </NCard>

    <NAlert v-if="error" type="error" style="margin-bottom: 24px;">{{ error }}</NAlert>
    <NAlert v-if="actionError" type="error" style="margin-bottom: 24px;">{{ actionError }}</NAlert>
    <NAlert v-if="actionMessage" type="success" style="margin-bottom: 24px;">{{ actionMessage }}</NAlert>

    <NEmpty v-if="!versions.length && !loading" :description="t('store.emptyVersions')" style="margin-top: 48px;" />

    <NGrid x-gap="16" y-gap="16" cols="1 s:2 m:3" responsive="screen">
      <NGi v-for="version in versions" :key="version.version">
        <NCard>
          <div style="display: flex; flex-direction: column; gap: 8px; height: 100%;">
            <NText style="font-size: 16px; font-weight: 600;">{{ version.version }}</NText>
            <NText depth="3" style="font-size: 13px;">{{ version.description || t('store.noDescription') }}</NText>
            <NText depth="3" style="font-size: 12px; margin-top: 8px;">{{ t('store.updatedAt') }}: {{ version.updated_at_display || '-' }}</NText>
            <NText depth="3" style="font-size: 12px;">{{ t('store.size') }}: {{ version.artifact_size_display || '0 kB' }}</NText>

            <div style="display: flex; gap: 8px; margin-top: 16px; width: 100%;">
              <NButton
                type="primary"
                size="small"
                style="flex: 1; min-width: 0;"
                :loading="Boolean(actingByVersion[version.version])"
                @click="downloadAndInstallVersion(version.version)"
              >
                <template #icon><NIcon><Download /></NIcon></template>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                  {{ t('store.downloadAndInstall') }}
                </span>
              </NButton>
              <NButton
                secondary
                size="small"
                style="flex-shrink: 0;"
                :title="t('store.downloadLocalTooltip')"
                :loading="Boolean(localDownloadingByVersion[version.version])"
                @click="downloadPackageToLocal(version.version)"
              >
                <template #icon><NIcon><ArrowDownToLine /></NIcon></template>
              </NButton>
            </div>

            <div v-if="getDownloadProgress(version.version) > 0" style="margin-top: 12px;">
               <NProgress type="line" :percentage="getDownloadProgress(version.version)" indicator-placement="inside" processing />
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <UploadInstallModal
      :visible="showUploadModal"
      :busy="uploadBusy"
      :error="uploadError"
      :status="uploadStatus"
      :status-done="uploadStatusDone"
      :output="uploadOutput"
      :file-name="uploadFileName"
      :hint="uploadHint"
      :show-file-picker="uploadShowFilePicker"
      :cancel-busy="uploadCancelBusy"
      :interactive-input="uploadInteractiveInput"
      :interactive-ready="uploadInteractiveReady"
      :interactive-mask-input="uploadInteractiveMaskInput"
      @close="closeUploadModal"
      @file-change="onUploadFileChange"
      @submit="submitUpload"
      @cancel-operation="cancelCurrentUpload"
      @interactive-input="setInteractiveInput"
      @interactive-mask-change="setInteractiveMaskInput"
      @interactive-submit="submitInteractiveInput"
    />
  </section>
</template>
