<script setup>
import { computed, onMounted, reactive } from 'vue'
import {
  robotState,
  getAppConfig,
  getAppVersions,
  installApp,
  refreshApps,
  saveAppConfig,
  setAppAutostart,
  startApp,
  stopApp,
  switchAppVersion,
  uninstallApp,
} from '../services/robotClient'

const localState = reactive({
  busyAppId: '',
  error: '',
  selectedAppId: '',
  expandedAppId: '',
  configBusy: false,
  configError: '',
  configOk: '',
  configVersion: 0,
  configDraft: {},
  configJsonText: '',
})

const installedMap = computed(() => {
  const map = new Map()
  for (const item of robotState.installedApps) {
    map.set(item.app_id, item)
  }
  return map
})

const catalogMap = computed(() => {
  const map = new Map()
  for (const item of robotState.appCatalog) {
    map.set(item.app_id, item)
  }
  return map
})

const catalogWithInstallInfo = computed(() => {
  return robotState.appCatalog.map((item) => {
    const install = installedMap.value.get(item.app_id)
    return {
      ...item,
      installed: Boolean(install),
      installInfo: install || null,
      task: findLatestTask(item.app_id),
    }
  })
})

const selectedAppMeta = computed(() => {
  if (!localState.selectedAppId) return null
  return catalogMap.value.get(localState.selectedAppId) || null
})

const schemaEntries = computed(() => {
  const props = selectedAppMeta.value?.manifest?.config_schema?.properties || {}
  return Object.entries(props)
})

function findLatestTask(appId) {
  const values = Object.values(robotState.appTaskById)
  const matched = values.filter((task) => task.app_id === appId)
  if (!matched.length) return null
  matched.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))
  return matched[0]
}

function setFieldValue(key, type, rawValue) {
  let value = rawValue
  if (type === 'integer') {
    value = Number.parseInt(rawValue, 10)
    if (!Number.isFinite(value)) value = 0
  } else if (type === 'number') {
    value = Number(rawValue)
    if (!Number.isFinite(value)) value = 0
  } else if (type === 'boolean') {
    value = Boolean(rawValue)
  } else {
    value = String(rawValue ?? '')
  }
  localState.configDraft = {
    ...localState.configDraft,
    [key]: value,
  }
}

async function doRefresh() {
  localState.error = ''
  try {
    await refreshApps()
  } catch (err) {
    localState.error = err.message
  }
}

async function doInstall(item) {
  localState.error = ''
  localState.busyAppId = item.app_id
  try {
    await installApp(item.app_id, item.manifest.runtime_optional)
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

async function toggleRunning(item, ev) {
  localState.error = ''
  localState.busyAppId = item.app_id
  const enabled = ev.target.checked
  try {
    if (enabled) {
      await startApp(item.app_id)
    } else {
      await stopApp(item.app_id)
    }
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

async function toggleAutostart(item, ev) {
  localState.error = ''
  localState.busyAppId = item.app_id
  try {
    await setAppAutostart(item.app_id, ev.target.checked)
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

async function doUninstall(item) {
  const yes = window.confirm(`确认卸载 ${item.app_id} ?`)
  if (!yes) return
  localState.error = ''
  localState.busyAppId = item.app_id
  try {
    await uninstallApp(item.app_id, false)
    if (localState.selectedAppId === item.app_id) {
      localState.selectedAppId = ''
      localState.configDraft = {}
      localState.configJsonText = ''
      localState.configVersion = 0
    }
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

async function openConfig(appId) {
  localState.selectedAppId = appId
  localState.configError = ''
  localState.configOk = ''
  localState.configBusy = true
  try {
    const cfg = await getAppConfig(appId, true)
    localState.configVersion = cfg.version || 0
    localState.configDraft = { ...(cfg.data || {}) }
    localState.configJsonText = JSON.stringify(localState.configDraft, null, 2)
  } catch (err) {
    localState.configError = err.message
  } finally {
    localState.configBusy = false
  }
}

async function saveSelectedConfig() {
  if (!localState.selectedAppId) return
  localState.configError = ''
  localState.configOk = ''
  localState.configBusy = true
  try {
    let payload = { ...localState.configDraft }
    if (!schemaEntries.value.length) {
      payload = JSON.parse(localState.configJsonText || '{}')
    }
    const result = await saveAppConfig(
      localState.selectedAppId,
      localState.configVersion,
      payload,
    )
    localState.configVersion = result.version
    localState.configDraft = { ...(result.config?.data || payload) }
    localState.configJsonText = JSON.stringify(localState.configDraft, null, 2)
    localState.configOk = `参数已保存，版本 ${result.version}`
  } catch (err) {
    localState.configError = err.message
  } finally {
    localState.configBusy = false
  }
}

async function toggleVersionPanel(appId) {
  if (localState.expandedAppId === appId) {
    localState.expandedAppId = ''
    return
  }
  localState.expandedAppId = appId
  try {
    await getAppVersions(appId)
  } catch (err) {
    localState.error = err.message
  }
}

async function doSwitchVersion(appId, version) {
  localState.error = ''
  localState.busyAppId = appId
  try {
    await switchAppVersion(appId, version, true)
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

async function doRemoveVersion(appId, version) {
  const yes = window.confirm(`确认删除 ${appId} 的版本 ${version} ?`)
  if (!yes) return
  localState.error = ''
  localState.busyAppId = appId
  try {
    await uninstallApp(appId, false, version)
    await getAppVersions(appId)
  } catch (err) {
    localState.error = err.message
  } finally {
    localState.busyAppId = ''
  }
}

onMounted(() => {
  if (!robotState.appCatalog.length) {
    doRefresh()
  }
})
</script>

<template>
  <section class="apps-layout">
    <article class="card">
      <div class="row-title">
        <h2>应用商店</h2>
        <button class="btn" @click="doRefresh">刷新</button>
      </div>
      <p class="tip">点击安装后可直接通过滑块启动，并设置开机自启动。</p>

      <div class="app-grid">
        <div v-for="item in catalogWithInstallInfo" :key="item.app_id" class="app-item">
          <div class="app-main">
            <h3>{{ item.manifest.name }} <small>({{ item.app_id }})</small></h3>
            <p class="tip">{{ item.manifest.description }}</p>
            <p class="tip">版本 {{ item.manifest.version }} | 运行模式 {{ item.manifest.runtime }}</p>
            <p v-if="item.task" class="tip">
              安装任务：{{ item.task.status }} / {{ item.task.progress }}% - {{ item.task.message }}
            </p>
          </div>
          <div class="app-actions">
            <button
              class="btn"
              :disabled="item.installed || localState.busyAppId === item.app_id"
              @click="doInstall(item)"
            >
              {{ item.installed ? '已安装' : '下载安装' }}
            </button>
          </div>
        </div>
      </div>
    </article>

    <article class="card">
      <h2>已安装应用</h2>
      <div class="app-grid" v-if="robotState.installedApps.length">
        <div v-for="item in robotState.installedApps" :key="item.app_id" class="app-item">
          <div class="app-main">
            <h3>{{ item.app_id }}</h3>
            <p class="tip">
              当前版本：v{{ item.active_version || '?' }}
              <span v-if="item.versions && item.versions.length > 1">
                (共 {{ item.versions.length }} 个版本)
              </span>
            </p>
            <p class="tip">状态：{{ item.status }} | 运行中：{{ item.running ? '是' : '否' }}</p>
          </div>
          <div class="toggle-group">
            <label class="switch-line">
              <span>启动滑块</span>
              <input
                type="checkbox"
                :checked="item.running"
                :disabled="localState.busyAppId === item.app_id"
                @change="toggleRunning(item, $event)"
              />
            </label>
            <label class="switch-line">
              <span>开机自启动</span>
              <input
                type="checkbox"
                :checked="item.autostart"
                :disabled="localState.busyAppId === item.app_id"
                @change="toggleAutostart(item, $event)"
              />
            </label>
            <button class="btn" :disabled="localState.busyAppId === item.app_id" @click="toggleVersionPanel(item.app_id)">
              {{ localState.expandedAppId === item.app_id ? '收起版本' : '版本管理' }}
            </button>
            <button class="btn" :disabled="localState.busyAppId === item.app_id" @click="openConfig(item.app_id)">
              参数设置
            </button>
            <button class="btn danger" :disabled="localState.busyAppId === item.app_id" @click="doUninstall(item)">
              卸载全部
            </button>
          </div>
          <div v-if="localState.expandedAppId === item.app_id" class="version-panel">
            <div
              v-for="ver in (robotState.appVersionsByAppId[item.app_id]?.versions || item.versions || [])"
              :key="ver"
              class="version-row"
            >
              <span class="version-label">v{{ ver }}</span>
              <span
                v-if="ver === (robotState.appVersionsByAppId[item.app_id]?.active_version || item.active_version)"
                class="badge active"
              >Active</span>
              <button
                v-else
                class="btn small"
                :disabled="localState.busyAppId === item.app_id"
                @click="doSwitchVersion(item.app_id, ver)"
              >激活</button>
              <button
                class="btn small danger"
                :disabled="localState.busyAppId === item.app_id || (item.versions && item.versions.length <= 1)"
                @click="doRemoveVersion(item.app_id, ver)"
              >删除</button>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="tip">暂无已安装应用。</p>
    </article>

    <article class="card" v-if="selectedAppMeta">
      <h2>参数设置 - {{ selectedAppMeta.manifest.name }}</h2>
      <p class="tip">版本：{{ localState.configVersion }}</p>
      <div class="config-form" v-if="schemaEntries.length">
        <div class="form-row" v-for="entry in schemaEntries" :key="entry[0]">
          <label>{{ entry[0] }}</label>
          <input
            v-if="entry[1].type !== 'boolean'"
            :type="entry[1].type === 'integer' || entry[1].type === 'number' ? 'number' : 'text'"
            :value="localState.configDraft[entry[0]]"
            @input="setFieldValue(entry[0], entry[1].type, $event.target.value)"
          />
          <input
            v-else
            type="checkbox"
            :checked="Boolean(localState.configDraft[entry[0]])"
            @change="setFieldValue(entry[0], entry[1].type, $event.target.checked)"
          />
        </div>
      </div>
      <div v-else>
        <p class="tip">该应用未提供结构化 schema，按 JSON 保存。</p>
        <textarea
          rows="8"
          v-model="localState.configJsonText"
        />
      </div>
      <div class="actions">
        <button class="btn" :disabled="localState.configBusy" @click="saveSelectedConfig">保存参数</button>
      </div>
      <p class="ok" v-if="localState.configOk">{{ localState.configOk }}</p>
      <p class="error" v-if="localState.configError">{{ localState.configError }}</p>
    </article>

    <p class="error" v-if="localState.error">{{ localState.error }}</p>
    <p class="error" v-if="robotState.appsError">{{ robotState.appsError }}</p>
  </section>
</template>
