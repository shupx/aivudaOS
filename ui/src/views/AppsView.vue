<script setup>
import AppCard from '../components/apps/AppCard.vue'
import { useAppsPanel } from '../composables/useAppsPanel'

const {
  apps,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadFileName,
  openUploadModal,
  closeUploadModal,
  onUploadFileChange,
  submitUpload,
} = useAppsPanel()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>应用菜单</h2>
      <div class="panel-actions wrap">
        <button class="link-btn" @click="openUploadModal">手动上传新应用安装包</button>
        <button class="btn" :disabled="loading" @click="refresh">
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!apps.length && !loading" class="empty-box">
      当前没有已安装应用
    </div>

    <div class="apps-grid">
      <AppCard
        v-for="app in apps"
        :key="app.app_id"
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <div v-if="showUploadModal" class="modal-overlay" @click.self="closeUploadModal">
      <section class="modal-card">
        <header class="modal-header">
          <h3>上传新应用安装包</h3>
        </header>

        <div class="field">
          <label>安装包文件（.tar.gz / .zip）</label>
          <input
            class="file-input"
            type="file"
            accept=".tar.gz,.zip"
            @change="onUploadFileChange($event.target.files)"
          >
          <p class="muted">{{ uploadFileName || '未选择文件' }}</p>
        </div>

        <p v-if="uploadError" class="error-text">{{ uploadError }}</p>

        <footer class="panel-actions">
          <button class="btn" :disabled="uploadBusy" @click="closeUploadModal">取消</button>
          <button class="btn primary" :disabled="uploadBusy || !uploadFileName" @click="submitUpload">
            {{ uploadBusy ? '上传中...' : '上传并安装' }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
