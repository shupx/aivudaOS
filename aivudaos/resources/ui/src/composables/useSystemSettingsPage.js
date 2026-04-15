import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { logout } from '../services/core/auth'
import {
  buildCaddyLocalCaDownloadUrl,
  fetchAptSourcesBackups,
  fetchAptSourcesList,
  fetchAivudaosServiceStatus,
  fetchOsConfig,
  fetchSudoNopasswdSetting,
  restoreAptSourcesBackup,
  setAivudaosServiceAutostart,
  triggerAivudaosServiceAction,
  triggerRelogin,
  updateAptSourcesList,
  updateOsConfig,
  updateSudoNopasswdSetting,
} from '../services/core/config'

export function useSystemSettingsPage() {
  const { t } = useI18n()
  const router = useRouter()

  const loading = ref(false)
  const saving = ref(false)
  const reloginPending = ref(false)
  const error = ref('')
  const success = ref('')
  const successLinks = ref([])
  const username = ref('')
  const enabled = ref(false)
  const serviceInstalled = ref(false)
  const serviceRunning = ref(false)
  const serviceAutostartEnabled = ref(false)
  const serviceActionPending = ref('')
  const caddyLocalCaDownloadUrl = computed(() => buildCaddyLocalCaDownloadUrl())
  const caddyLocalCaHintVisible = ref(false)
  const osDraftData = ref({})
  const osOriginalData = ref({})
  const osVersion = ref(0)
  const osCellErrors = ref({})
  
  // Modal state
  const showPasswordModal = ref(false)
  const sudoPassword = ref('')
  const showSudoPassword = ref(false)
  const pendingToggleValue = ref(false)

  const showAptSourcesModal = ref(false)
  const aptSourcesLoading = ref(false)
  const aptSourcesWriting = ref(false)
  const aptSourcesText = ref('')
  const aptSourcesPath = ref('/etc/apt/sources.list')
  const aptSudoPassword = ref('')
  const showAptSudoPassword = ref(false)
  const showAptPasswordModal = ref(false)
  const aptPendingAction = ref('')
  const aptBackups = ref([])
  const selectedAptBackupId = ref('')
  const aptUpdateOutput = ref('')
  const aptEditorTextRef = ref(null)
  const aptEditorHighlightRef = ref(null)

  const aptSourceLines = computed(() => {
    const text = String(aptSourcesText.value || '')
    const lines = text.split(/\r?\n/)
    return lines.map((line, index) => ({
      key: `apt-line-${index}`,
      text: line,
      comment: /^\s*#/.test(line),
    }))
  })

  const osRows = computed(() => flattenDataLeaves(osDraftData.value || {}))

  async function load() {
    loading.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []
    try {
      const [data, osData, serviceData] = await Promise.all([
        fetchSudoNopasswdSetting(),
        fetchOsConfig(),
        fetchAivudaosServiceStatus(),
      ])
      username.value = String(data?.username || '')
      enabled.value = Boolean(data?.enabled)
      serviceInstalled.value = Boolean(serviceData?.installed)
      serviceRunning.value = Boolean(serviceData?.running)
      serviceAutostartEnabled.value = Boolean(serviceData?.autostart_enabled)
      osDraftData.value = deepClone(osData?.data || {})
      osOriginalData.value = deepClone(osData?.data || {})
      osVersion.value = Number(osData?.version || 0)
      osCellErrors.value = {}
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  function toggleEnabled() {
    if (loading.value || saving.value) return
    pendingToggleValue.value = !enabled.value
    showPasswordModal.value = true
    sudoPassword.value = ''
    showSudoPassword.value = false
  }

  function closePasswordModal() {
    showPasswordModal.value = false
    sudoPassword.value = ''
    showSudoPassword.value = false
    pendingToggleValue.value = false
  }

  async function submitToggle() {
    saving.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []
    try {
      if (!sudoPassword.value.trim()) {
        error.value = t('systemSettings.sudoPasswordRequired')
        saving.value = false
        return
      }
      const data = await updateSudoNopasswdSetting(pendingToggleValue.value, sudoPassword.value)
      username.value = String(data?.username || username.value || '')
      enabled.value = Boolean(data?.enabled)
      success.value = t('systemSettings.saveSuccess')
      closePasswordModal()
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.saveFailed'))
    } finally {
      saving.value = false
    }
  }

  async function reloginNow() {
    if (loading.value || saving.value || reloginPending.value) return

    const confirmed = window.confirm(t('systemSettings.reloginWarning'))
    if (!confirmed) return

    reloginPending.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []

    try {
      await triggerRelogin()
      success.value = t('systemSettings.reloginTriggered')
      logout()
      router.replace('/login')
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.reloginFailed'))
    } finally {
      reloginPending.value = false
    }
  }

  async function toggleServiceAutostart(nextValue) {
    if (loading.value || saving.value || serviceActionPending.value) return

    const previousValue = Boolean(serviceAutostartEnabled.value)
    serviceAutostartEnabled.value = Boolean(nextValue)
    serviceActionPending.value = 'autostart'
    error.value = ''
    success.value = ''
    successLinks.value = []

    try {
      const resp = await setAivudaosServiceAutostart(nextValue)
      serviceInstalled.value = Boolean(resp?.installed)
      serviceRunning.value = Boolean(resp?.running)
      serviceAutostartEnabled.value = Boolean(resp?.autostart_enabled)
      success.value = nextValue
        ? t('systemSettings.serviceAutostartEnabledSuccess')
        : t('systemSettings.serviceAutostartDisabledSuccess')
    } catch (err) {
      serviceAutostartEnabled.value = previousValue
      error.value = String(err?.message || err || t('systemSettings.serviceAutostartFailed'))
    } finally {
      serviceActionPending.value = ''
    }
  }

  async function downloadCaddyLocalCa() {
    if (loading.value || saving.value) return

    caddyLocalCaHintVisible.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []

    try {
      const resp = await fetch(caddyLocalCaDownloadUrl.value, {
        method: 'HEAD',
      })

      if (!resp.ok) {
        throw new Error(await resolveCaddyLocalCaDownloadError(caddyLocalCaDownloadUrl.value, t))
      }

      const link = document.createElement('a')
      link.href = caddyLocalCaDownloadUrl.value
      link.rel = 'noopener'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.caddyLocalCaDownloadFailed'))
    }
  }

  async function triggerServiceAction(action) {
    if (loading.value || saving.value || serviceActionPending.value) return

    if (action === 'stop') {
      const confirmed = window.confirm(t('systemSettings.serviceStopWarning'))
      if (!confirmed) return
    }
    if (action === 'restart') {
      const confirmed = window.confirm(t('systemSettings.serviceRestartWarning'))
      if (!confirmed) return
    }
    if (action === 'uninstall') {
      const confirmed = window.confirm(t('systemSettings.serviceUninstallWarning'))
      if (!confirmed) return
    }

    serviceActionPending.value = action
    error.value = ''
    success.value = ''
    successLinks.value = []

    try {
      await triggerAivudaosServiceAction(action)
      if (action === 'stop') {
        serviceRunning.value = false
        success.value = t('systemSettings.serviceStopScheduled')
      } else if (action === 'restart') {
        success.value = t('systemSettings.serviceRestartScheduled')
      } else if (action === 'uninstall') {
        serviceInstalled.value = false
        serviceRunning.value = false
        serviceAutostartEnabled.value = false
        success.value = t('systemSettings.serviceUninstallScheduled')
      }
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.serviceActionFailed'))
    } finally {
      window.setTimeout(() => {
        if (serviceActionPending.value === action) {
          serviceActionPending.value = ''
        }
      }, 1500)
    }
  }

  async function openAptSourcesModal() {
    showAptSourcesModal.value = true
    aptSudoPassword.value = ''
    showAptSudoPassword.value = false
    aptUpdateOutput.value = ''
    selectedAptBackupId.value = ''
    await loadAptSources()
  }

  function closeAptSourcesModal() {
    showAptSourcesModal.value = false
    closeAptPasswordModal()
    aptUpdateOutput.value = ''
    selectedAptBackupId.value = ''
  }

  function openAptPasswordModal(action) {
    aptPendingAction.value = String(action || '').trim()
    aptSudoPassword.value = ''
    showAptSudoPassword.value = false
    showAptPasswordModal.value = true
  }

  function closeAptPasswordModal() {
    showAptPasswordModal.value = false
    aptPendingAction.value = ''
    aptSudoPassword.value = ''
    showAptSudoPassword.value = false
  }

  function syncAptEditorScroll() {
    const textNode = aptEditorTextRef.value
    const highlightNode = aptEditorHighlightRef.value
    if (!textNode || !highlightNode) {
      return
    }
    highlightNode.scrollTop = textNode.scrollTop
    highlightNode.scrollLeft = textNode.scrollLeft
  }

  async function loadAptSources() {
    aptSourcesLoading.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []
    try {
      const [sourcesResp, backupsResp] = await Promise.all([
        fetchAptSourcesList(),
        fetchAptSourcesBackups(),
      ])
      aptSourcesText.value = String(sourcesResp?.content || '')
      aptSourcesPath.value = String(sourcesResp?.path || '/etc/apt/sources.list')
      aptBackups.value = Array.isArray(backupsResp?.items) ? backupsResp.items : []
      selectedAptBackupId.value = String(aptBackups.value?.[0]?.backup_id || '')
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.aptLoadFailed'))
    } finally {
      aptSourcesLoading.value = false
    }
  }

  function requestWriteAptSources() {
    if (aptSourcesWriting.value || aptSourcesLoading.value) return
    openAptPasswordModal('write')
  }

  function requestRestoreAptSources() {
    if (aptSourcesWriting.value || aptSourcesLoading.value) return
    if (!selectedAptBackupId.value) {
      error.value = t('systemSettings.aptBackupRequired')
      return
    }
    openAptPasswordModal('restore')
  }

  async function submitAptAction() {
    if (aptSourcesWriting.value || aptSourcesLoading.value) return
    if (!aptSudoPassword.value.trim()) {
      error.value = t('systemSettings.sudoPasswordRequired')
      return
    }

    if (aptPendingAction.value === 'write') {
      await writeAptSources()
      return
    }

    if (aptPendingAction.value === 'restore') {
      await restoreAptSources()
      return
    }
  }

  async function writeAptSources() {
    if (aptSourcesWriting.value || aptSourcesLoading.value) return

    aptSourcesWriting.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []
    try {
      const resp = await updateAptSourcesList(aptSourcesText.value, aptSudoPassword.value)
      aptUpdateOutput.value = String(resp?.apt_update?.output || '')
      success.value = t('systemSettings.aptWriteSuccess')
      closeAptPasswordModal()
      await loadAptSources()
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.aptWriteFailed'))
    } finally {
      aptSourcesWriting.value = false
    }
  }

  async function restoreAptSources() {
    if (aptSourcesWriting.value || aptSourcesLoading.value) return
    if (!selectedAptBackupId.value) return

    const confirmed = window.confirm(t('systemSettings.aptRestoreConfirm'))
    if (!confirmed) return

    aptSourcesWriting.value = true
    error.value = ''
    success.value = ''
    successLinks.value = []
    try {
      const resp = await restoreAptSourcesBackup(selectedAptBackupId.value, aptSudoPassword.value)
      aptUpdateOutput.value = String(resp?.apt_update?.output || '')
      success.value = t('systemSettings.aptRestoreSuccess')
      closeAptPasswordModal()
      await loadAptSources()
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.aptRestoreFailed'))
    } finally {
      aptSourcesWriting.value = false
    }
  }

  function getOsCellValue(row) {
    return nestedGet(osDraftData.value || {}, row.path)
  }

  function getOsCellError(row) {
    return osCellErrors.value[cellErrorKey(row)] || ''
  }

  function displayOsValue(row) {
    return valueToInlineText(getOsCellValue(row))
  }

  async function onOsBooleanChange(row, checked) {
    await applyOsValue(row, Boolean(checked))
  }

  async function onOsEnumChange(row, value) {
    const option = getOsEnumOptions(row).find((item) => item.value === value)
    if (!option || option.disabled) {
      return
    }
    await applyOsValue(row, option.value)
  }

  async function onOsTextChange(row, rawText) {
    try {
      const next = parseValueByType(rawText, row.type)
      await applyOsValue(row, next)
    } catch (err) {
      osCellErrors.value = {
        ...osCellErrors.value,
        [cellErrorKey(row)]: String(err?.message || err || t('systemSettings.osInvalidValue')),
      }
    }
  }

  async function applyOsValue(row, nextValue) {
    if (isOsValueSelectionBlocked(row, nextValue)) {
      error.value = t('systemSettings.osOptionNotAllowed')
      return
    }

    const beforeData = deepClone(osDraftData.value || {})
    const beforeValue = nestedGet(beforeData, row.path)
    if (row.path === 'avahi_hostname' && !isValueEqual(beforeValue, nextValue)) {
      const confirmed = window.confirm(t('systemSettings.avahiHostnameChangeConfirm'))
      if (!confirmed) {
        osDraftData.value = beforeData
        success.value = t('systemSettings.avahiHostnameChangeCanceled')
        successLinks.value = []
        return
      }
    }

    const nextData = deepClone(osDraftData.value || {})
    nestedSet(nextData, row.path, nextValue)
    osDraftData.value = nextData

    const key = cellErrorKey(row)
    if (osCellErrors.value[key]) {
      const nextErrors = { ...osCellErrors.value }
      delete nextErrors[key]
      osCellErrors.value = nextErrors
    }

    error.value = ''
    success.value = ''
    successLinks.value = []

    try {
      const resp = await updateOsConfig(deepClone(nextData), Number(osVersion.value || 0))
      osVersion.value = Number(resp?.version || osVersion.value || 0)
      osOriginalData.value = deepClone(nextData)
      const saveSuccess = buildOsSaveSuccessResult({
        row,
        beforeValue,
        nextValue,
        nextData,
        t,
      })
      success.value = saveSuccess.message
      successLinks.value = saveSuccess.links
    } catch (err) {
      const message = appendSudoHintIfNeeded({
        message: String(err?.message || err || t('systemSettings.osSaveFailed')),
        t,
      })
      osDraftData.value = beforeData
      await load()
      error.value = message
      successLinks.value = []
    }
  }

  onMounted(() => {
    load()
  })

  return {
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
  }
}

function getOsEnumOptions(row) {
  const path = String(row?.path || '')
  if (path === 'runtime_process_manager') {
    return [
      { value: 'auto', disabled: false },
      { value: 'systemd', disabled: false },
      { value: 'popen', disabled: true },
    ]
  }
  if (path === 'runtime_systemd_scope') {
    return [
      { value: 'user', disabled: false },
      { value: 'system', disabled: true },
    ]
  }
  return []
}

async function resolveCaddyLocalCaDownloadError(url, t) {
  try {
    const resp = await fetch(url, {
      method: 'GET',
    })
    const text = await resp.text()
    let payload = text

    try {
      payload = text ? JSON.parse(text) : null
    } catch {
      payload = text
    }

    return String(payload?.detail || payload || t('systemSettings.caddyLocalCaDownloadFailed'))
  } catch {
    return t('systemSettings.caddyLocalCaDownloadFailed')
  }
}

function isOsValueSelectionBlocked(row, value) {
  const options = getOsEnumOptions(row)
  if (!options.length) {
    return false
  }
  const matched = options.find((item) => item.value === value)
  if (!matched) {
    return true
  }
  return matched.disabled
}

function parseValueByType(rawText, type) {
  if (type === 'string') {
    return String(rawText || '')
  }

  if (type === 'integer') {
    if (rawText === '' || rawText === null || rawText === undefined) {
      throw new Error('integer required')
    }
    const value = Number(rawText)
    if (!Number.isInteger(value)) {
      throw new Error('must be integer')
    }
    return value
  }

  if (type === 'number') {
    if (rawText === '' || rawText === null || rawText === undefined) {
      throw new Error('number required')
    }
    const value = Number(rawText)
    if (!Number.isFinite(value)) {
      throw new Error('must be number')
    }
    return value
  }

  if (type === 'boolean') {
    const text = String(rawText || '').trim().toLowerCase()
    if (text === 'true' || text === '1') return true
    if (text === 'false' || text === '0') return false
    throw new Error('must be boolean')
  }

  if (type === 'array' || type === 'object') {
    const parsed = JSON.parse(String(rawText || 'null'))
    if (type === 'array' && !Array.isArray(parsed)) {
      throw new Error('must be array JSON')
    }
    if (type === 'object' && (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))) {
      throw new Error('must be object JSON')
    }
    return parsed
  }

  if (type === 'null') {
    return null
  }

  try {
    return JSON.parse(String(rawText || 'null'))
  } catch {
    return String(rawText || '')
  }
}

function flattenDataLeaves(data, parentPath = '') {
  if (!isRecord(data)) {
    if (!parentPath || String(parentPath).startsWith('_')) {
      return []
    }
    return [{
      path: parentPath,
      value: data,
      type: inferValueType(data),
    }]
  }

  const rows = []
  for (const [key, child] of Object.entries(data)) {
    if (String(key).startsWith('_')) {
      continue
    }
    const childPath = parentPath ? `${parentPath}.${key}` : key
    if (isRecord(child)) {
      rows.push(...flattenDataLeaves(child, childPath))
      continue
    }
    rows.push({
      path: childPath,
      value: child,
      type: inferValueType(child),
    })
  }
  return rows
}

function nestedGet(data, dottedPath) {
  if (!dottedPath) return data
  const segments = String(dottedPath).split('.')
  let cursor = data
  for (const segment of segments) {
    if (!isRecord(cursor) || !(segment in cursor)) {
      return undefined
    }
    cursor = cursor[segment]
  }
  return cursor
}

function nestedSet(data, dottedPath, value) {
  const segments = String(dottedPath || '').split('.').filter(Boolean)
  if (!segments.length) return

  let cursor = data
  for (let index = 0; index < segments.length - 1; index += 1) {
    const key = segments[index]
    if (!isRecord(cursor[key])) {
      cursor[key] = {}
    }
    cursor = cursor[key]
  }

  cursor[segments[segments.length - 1]] = value
}

function valueToInlineText(value) {
  if (value === undefined) return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value ?? null))
}

function isValueEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

function inferValueType(value) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number'
  if (typeof value === 'string') return 'string'
  if (isRecord(value)) return 'object'
  return 'unknown'
}

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function cellErrorKey(row) {
  return `os:${row.path}`
}

function appendSudoHintIfNeeded({ message, t }) {
  const text = String(message || '')
  const lowered = text.toLowerCase()
  const hasSudo = lowered.includes('sudo')
  const hasPasswordIssue =
    lowered.includes('password') ||
    lowered.includes('a password is required') ||
    lowered.includes('sudo:')

  if (!hasSudo || !hasPasswordIssue) {
    return text
  }

  const hint = String(t('systemSettings.sudoNopasswdHint') || '').trim()
  if (!hint || text.includes(hint)) {
    return text
  }
  return `${text} ${hint}`
}

function buildOsSaveSuccessResult({ row, beforeValue, nextValue, nextData, t }) {
  const base = String(t('systemSettings.osSaveSuccess') || 'OS parameters saved')
  if (row?.path !== 'avahi_hostname' || isValueEqual(beforeValue, nextValue)) {
    return { message: base, links: [] }
  }

  const hostname = String(nestedGet(nextData || {}, 'avahi_hostname') || '')
    .trim()
    .toLowerCase()
  if (!hostname) {
    return { message: base, links: [] }
  }

  return {
    message: `${base} ${t('systemSettings.avahiHostnameUpdatedNotice')}`,
    links: [
      { url: `https://${hostname}.local`, label: `https://${hostname}.local` },
      { url: 'http://127.0.0.1:80', label: 'http://127.0.0.1:80' },
    ],
  }
}
