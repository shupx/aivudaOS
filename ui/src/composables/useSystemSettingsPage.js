import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { logout } from '../services/core/auth'
import {
  fetchOsConfig,
  fetchSudoNopasswdSetting,
  triggerAvahiRestart,
  triggerRelogin,
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
  const username = ref('')
  const enabled = ref(false)
  const osDraftData = ref({})
  const osOriginalData = ref({})
  const osVersion = ref(0)
  const osCellErrors = ref({})
  
  // Modal state
  const showPasswordModal = ref(false)
  const sudoPassword = ref('')
  const showSudoPassword = ref(false)
  const pendingToggleValue = ref(false)

  const osRows = computed(() => flattenDataLeaves(osDraftData.value || {}))

  async function load() {
    loading.value = true
    error.value = ''
    success.value = ''
    try {
      const [data, osData] = await Promise.all([fetchSudoNopasswdSetting(), fetchOsConfig()])
      username.value = String(data?.username || '')
      enabled.value = Boolean(data?.enabled)
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

    try {
      const resp = await updateOsConfig(deepClone(nextData), Number(osVersion.value || 0))
      osVersion.value = Number(resp?.version || osVersion.value || 0)
      osOriginalData.value = deepClone(nextData)
      success.value = t('systemSettings.osSaveSuccess')

      if (row.path === 'avahi_hostname' && !isValueEqual(beforeValue, nextValue)) {
        await maybeRestartAvahi()
      }
    } catch (err) {
      osDraftData.value = beforeData
      error.value = String(err?.message || err || t('systemSettings.osSaveFailed'))
    }
  }

  async function maybeRestartAvahi() {
    const confirmed = window.confirm(t('systemSettings.avahiRestartConfirm'))
    if (!confirmed) {
      success.value = t('systemSettings.avahiRestartPending')
      return
    }

    try {
      await triggerAvahiRestart()
      success.value = t('systemSettings.avahiRestartSuccess')
    } catch (err) {
      error.value = String(err?.message || err || t('systemSettings.avahiRestartFailed'))
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
    username,
    enabled,
    toggleEnabled,
    showPasswordModal,
    closePasswordModal,
    sudoPassword,
    showSudoPassword,
    submitToggle,
    reloginNow,
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
