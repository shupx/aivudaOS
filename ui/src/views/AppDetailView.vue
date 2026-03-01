<script setup>
import AppCard from '../components/apps/AppCard.vue'
import { useAppDetailPage } from '../composables/useAppDetailPage'

const {
  app,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
  logText,
  logBusy,
  logError,
  loadLogs,
  clearAndReloadLogs,
  actionBusy,
  actionError,
  actionMessage,
  versions,
  selectedVersion,
  switchWithRestart,
  canSwitchVersion,
  onUpgradeFileChange,
  selectedFileName,
  canUpgrade,
  runUpgrade,
  uninstallVersionOnly,
  uninstallPurge,
  canUninstall,
  runUninstall,
  runSwitchVersion,
  backToList,
} = useAppDetailPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>应用详情</h2>
      <div class="panel-actions">
        <button class="btn" @click="backToList">返回列表</button>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="refresh">
          {{ loading ? '...' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!app && !loading" class="empty-box">
      未找到该应用或应用未安装
    </div>

    <div v-else-if="app" class="apps-grid">
      <AppCard
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        :clickable="false"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <article v-if="app" class="log-panel">
      <header class="log-header">
        <h3>输出</h3>
        <div class="panel-actions">
          <button class="btn btn-stable-log" :disabled="logBusy" @click="loadLogs">
            {{ logBusy ? '读取中...' : '拉取最新' }}
          </button>
          <button class="btn" @click="clearAndReloadLogs">清空并重读</button>
        </div>
      </header>

      <p v-if="logError" class="error-text">{{ logError }}</p>
      <pre class="log-output">{{ logText || '暂无输出' }}</pre>
    </article>

    <article v-if="app" class="actions-panel">
      <header class="log-header">
        <h3>应用操作</h3>
      </header>

      <p v-if="actionError" class="error-text">{{ actionError }}</p>
      <p v-if="actionMessage" class="ok-text">{{ actionMessage }}</p>

      <div class="actions-grid">
        <div class="action-block">
          <h4>上传新版本</h4>
          <div class="panel-actions wrap">
            <input
              class="file-input"
              type="file"
              accept=".tar.gz,.zip"
              @change="onUpgradeFileChange($event.target.files)"
            >
            <button class="btn" :disabled="!canUpgrade" @click="runUpgrade">
              {{ actionBusy ? '处理中...' : '上传并升级' }}
            </button>
          </div>
          <p class="muted">{{ selectedFileName || '未选择文件' }}</p>
        </div>

        <div class="action-block">
          <h4>切换版本</h4>
          <div class="panel-actions wrap">
            <select v-model="selectedVersion" class="select-input">
              <option v-for="version in versions" :key="version" :value="version">
                {{ version }}
              </option>
            </select>
            <label class="check-item">
              <input v-model="switchWithRestart" type="checkbox">
              切换后重启
            </label>
            <button class="btn" :disabled="!canSwitchVersion || actionBusy" @click="runSwitchVersion">
              {{ actionBusy ? '处理中...' : '切换版本' }}
            </button>
          </div>
        </div>

        <div class="action-block action-block-wide">
          <h4>卸载</h4>
          <div class="panel-actions wrap">
            <label class="check-item">
              <input v-model="uninstallVersionOnly" type="checkbox">
              仅卸载当前版本
            </label>
            <label class="check-item">
              <input v-model="uninstallPurge" type="checkbox">
              清理配置
            </label>
            <button class="btn danger" :disabled="!canUninstall" @click="runUninstall">
              {{ actionBusy ? '处理中...' : '执行卸载' }}
            </button>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
