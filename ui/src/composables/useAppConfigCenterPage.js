import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchActiveAppConfigs, updateAppConfig } from '../services/core/apps'

export function useAppConfigCenterPage() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()

  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const success = ref('')

  const appItems = ref([])
  const draftByApp = ref({})
  const originalByApp = ref({})
  const revisionByApp = ref({})
  const appVersionByApp = ref({})
  const schemaByApp = ref({})
  const selectedAppId = ref('')

  const showConfirmModal = ref(false)
  const pendingChanges = ref([])
  const cellErrors = ref({})

  const appOptions = computed(() => {
    return appItems.value.map((item) => ({
      appId: item.app_id,
      name: item.name || item.app_id,
      version: item.app_version || '-',
    }))
  })

  const appThemeById = computed(() => {
    const classes = ['config-row-app-0', 'config-row-app-1', 'config-row-app-2', 'config-row-app-3']
    const mapping = {}
    appItems.value.forEach((item, index) => {
      const appId = String(item?.app_id || '')
      if (!appId) return
      mapping[appId] = classes[index % classes.length]
    })
    return mapping
  })

  const rows = computed(() => {
    const selected = selectedAppId.value
    const result = []

    for (const app of appItems.value) {
      if (selected && app.app_id !== selected) continue

      const schema = schemaByApp.value[app.app_id] || {}
      const appData = draftByApp.value[app.app_id] || {}
      const appRows = flattenSchema(schema, appData, {
        appId: app.app_id,
        appName: app.name || app.app_id,
        appVersion: app.app_version || '',
      })
      result.push(...appRows)
    }

    return result
  })

  const hasChanges = computed(() => collectChanges().length > 0)

  async function loadAllConfigs() {
    loading.value = true
    error.value = ''
    success.value = ''

    try {
      const data = await fetchActiveAppConfigs()
      const items = Array.isArray(data?.items) ? data.items : []
      appItems.value = items

      const nextDraft = {}
      const nextOriginal = {}
      const nextRevision = {}
      const nextVersion = {}
      const nextSchema = {}

      for (const item of items) {
        const appId = String(item?.app_id || '')
        if (!appId) continue

        const appData = deepClone(item?.data || {})
        nextDraft[appId] = appData
        nextOriginal[appId] = deepClone(appData)
        nextRevision[appId] = Number(item?.version || 0)
        nextVersion[appId] = String(item?.app_version || '')
        nextSchema[appId] = item?.normalized_schema || item?.schema || {}
      }

      draftByApp.value = nextDraft
      originalByApp.value = nextOriginal
      revisionByApp.value = nextRevision
      appVersionByApp.value = nextVersion
      schemaByApp.value = nextSchema

      const queryAppId = String(route.query.app_id || '')
      if (queryAppId && nextDraft[queryAppId]) {
        selectedAppId.value = queryAppId
      } else if (selectedAppId.value && nextDraft[selectedAppId.value]) {
        selectedAppId.value = selectedAppId.value
      } else {
        selectedAppId.value = ''
      }

      cellErrors.value = {}
    } catch (err) {
      error.value = String(err?.message || err || t('appConfigCenter.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  function getCellValue(row) {
    const appData = draftByApp.value[row.appId] || {}
    return nestedGet(appData, row.path)
  }

  function getCellError(row) {
    return cellErrors.value[cellErrorKey(row)] || ''
  }

  function getDefaultText(row) {
    if (!row.hasDefault) return '-'
    return valueToInlineText(row.defaultValue)
  }

  function getRangeText(row) {
    return row.rangeText || '-'
  }

  function getDescriptionText(row) {
    return row.description || '-'
  }

  function displayValue(row) {
    return valueToInlineText(getCellValue(row))
  }

  function onBooleanChange(row, checked) {
    applyValue(row, Boolean(checked))
  }

  function onEnumChange(row, indexText) {
    const index = Number(indexText)
    if (!Number.isInteger(index) || !Array.isArray(row.enumValues) || index < 0 || index >= row.enumValues.length) {
      return
    }
    applyValue(row, deepClone(row.enumValues[index]))
  }

  function onTextChange(row, rawText) {
    try {
      const next = parseValueByType(rawText, row.type)
      applyValue(row, next)
    } catch (err) {
      cellErrors.value = {
        ...cellErrors.value,
        [cellErrorKey(row)]: String(err?.message || err || t('appConfigCenter.invalidValue')),
      }
    }
  }

  function applyValue(row, nextValue) {
    const appData = deepClone(draftByApp.value[row.appId] || {})
    nestedSet(appData, row.path, nextValue)
    draftByApp.value = {
      ...draftByApp.value,
      [row.appId]: appData,
    }

    const key = cellErrorKey(row)
    if (cellErrors.value[key]) {
      const nextErrors = { ...cellErrors.value }
      delete nextErrors[key]
      cellErrors.value = nextErrors
    }

    error.value = ''
    success.value = ''
  }

  function openSaveConfirm() {
    error.value = ''
    success.value = ''

    const hasCellError = Object.values(cellErrors.value).some((item) => Boolean(item))
    if (hasCellError) {
      error.value = t('appConfigCenter.fixCellErrorsFirst')
      return
    }

    const changes = collectChanges()
    if (!changes.length) {
      error.value = t('appConfigCenter.noChanges')
      return
    }

    pendingChanges.value = changes
    showConfirmModal.value = true
  }

  function closeSaveConfirm() {
    if (saving.value) return
    showConfirmModal.value = false
  }

  async function confirmSave() {
    if (saving.value) return

    const changes = pendingChanges.value
    if (!changes.length) {
      showConfirmModal.value = false
      return
    }

    saving.value = true
    error.value = ''
    success.value = ''

    const changedAppIds = [...new Set(changes.map((item) => item.appId))]
    const failed = []

    for (const appId of changedAppIds) {
      try {
        const resp = await updateAppConfig(appId, {
          version: Number(revisionByApp.value[appId] || 0),
          app_version: appVersionByApp.value[appId] || '',
          data: deepClone(draftByApp.value[appId] || {}),
        })

        revisionByApp.value = {
          ...revisionByApp.value,
          [appId]: Number(resp?.version || revisionByApp.value[appId] || 0),
        }

        originalByApp.value = {
          ...originalByApp.value,
          [appId]: deepClone(draftByApp.value[appId] || {}),
        }
      } catch (err) {
        failed.push({
          appId,
          message: String(err?.message || err || t('appConfigCenter.saveFailed')),
        })
      }
    }

    saving.value = false
    showConfirmModal.value = false

    if (failed.length) {
      error.value = failed.map((item) => `${item.appId}: ${item.message}`).join('; ')
      success.value = ''
      return
    }

    success.value = t('appConfigCenter.saveSuccess')
  }

  function collectChanges() {
    const output = []
    const currentRows = rows.value

    for (const row of currentRows) {
      const before = nestedGet(originalByApp.value[row.appId] || {}, row.path)
      const after = nestedGet(draftByApp.value[row.appId] || {}, row.path)
      if (isValueEqual(before, after)) {
        continue
      }
      output.push({
        appId: row.appId,
        appName: row.appName,
        path: row.path,
        before,
        after,
      })
    }

    return output
  }

  function goBackApps() {
    router.push('/dashboard/apps')
  }

  function getRowThemeClass(appId) {
    return appThemeById.value[String(appId || '')] || 'config-row-app-0'
  }

  watch(
    () => route.query.app_id,
    (next) => {
      const nextId = String(next || '')
      if (nextId === selectedAppId.value) return
      selectedAppId.value = nextId
    },
    { immediate: true },
  )

  watch(
    () => selectedAppId.value,
    (next) => {
      const appId = String(next || '')
      const current = String(route.query.app_id || '')
      if (appId === current) return

      router.replace({
        path: route.path,
        query: {
          ...route.query,
          app_id: appId || undefined,
        },
      })
    },
  )

  loadAllConfigs()

  return {
    loading,
    saving,
    error,
    success,
    appOptions,
    selectedAppId,
    rows,
    hasChanges,
    showConfirmModal,
    pendingChanges,
    loadAllConfigs,
    openSaveConfirm,
    closeSaveConfirm,
    confirmSave,
    goBackApps,
    getCellValue,
    getCellError,
    displayValue,
    getDefaultText,
    getRangeText,
    getDescriptionText,
    getRowThemeClass,
    onBooleanChange,
    onEnumChange,
    onTextChange,
    valueToInlineText,
  }
}

function flattenSchema(schema, data, appInfo, parentPath = '') {
  if (!schema || typeof schema !== 'object') {
    return []
  }

  const type = normalizeType(schema.type)
  const properties = isRecord(schema.properties) ? schema.properties : null
  const rows = []

  if ((type === 'object' || properties) && properties) {
    for (const [key, childSchema] of Object.entries(properties)) {
      if (!isRecord(childSchema)) {
        continue
      }
      const childPath = parentPath ? `${parentPath}.${key}` : key
      rows.push(...flattenSchema(childSchema, data, appInfo, childPath))
    }
    return rows
  }

  if (!parentPath) {
    return rows
  }

  const enumValues = Array.isArray(schema.enum) ? schema.enum : []
  const rangeText = buildRangeText(schema, type)

  rows.push({
    appId: appInfo.appId,
    appName: appInfo.appName,
    appVersion: appInfo.appVersion,
    path: parentPath,
    type,
    enumValues,
    rangeText,
    description: typeof schema.description === 'string' ? schema.description : '',
    defaultValue: schema.default,
    hasDefault: Object.prototype.hasOwnProperty.call(schema, 'default'),
    currentValue: nestedGet(data, parentPath),
  })

  return rows
}

function buildRangeText(schema, type) {
  const segments = []

  if (Array.isArray(schema.enum) && schema.enum.length) {
    segments.push(`enum: ${schema.enum.map((item) => valueToInlineText(item)).join(', ')}`)
  }

  if (type === 'integer' || type === 'number') {
    if (isNumber(schema.minimum)) {
      segments.push(`>= ${schema.minimum}`)
    }
    if (isNumber(schema.maximum)) {
      segments.push(`<= ${schema.maximum}`)
    }
    if (isNumber(schema.exclusiveMinimum)) {
      segments.push(`> ${schema.exclusiveMinimum}`)
    }
    if (isNumber(schema.exclusiveMaximum)) {
      segments.push(`< ${schema.exclusiveMaximum}`)
    }
  }

  if (type === 'string') {
    if (isInteger(schema.minLength)) {
      segments.push(`len >= ${schema.minLength}`)
    }
    if (isInteger(schema.maxLength)) {
      segments.push(`len <= ${schema.maxLength}`)
    }
    if (typeof schema.pattern === 'string' && schema.pattern) {
      segments.push(`pattern: ${schema.pattern}`)
    }
  }

  if (type === 'array') {
    if (isInteger(schema.minItems)) {
      segments.push(`items >= ${schema.minItems}`)
    }
    if (isInteger(schema.maxItems)) {
      segments.push(`items <= ${schema.maxItems}`)
    }
    if (schema.items && typeof schema.items === 'object') {
      const itemType = normalizeType(schema.items.type)
      if (itemType) {
        segments.push(`item type: ${itemType}`)
      }
    }
  }

  return segments.join('; ')
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

function normalizeType(typeValue) {
  if (Array.isArray(typeValue) && typeValue.length) {
    const stringType = typeValue.find((item) => typeof item === 'string')
    return stringType || ''
  }
  if (typeof typeValue === 'string') {
    return typeValue
  }
  return ''
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
  if (!segments.length) {
    return
  }

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

function deepClone(value) {
  return JSON.parse(JSON.stringify(value ?? null))
}

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function valueToInlineText(value) {
  if (value === undefined) return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function isValueEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

function cellErrorKey(row) {
  return `${row.appId}:${row.path}`
}

function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function isInteger(value) {
  return Number.isInteger(value)
}
