import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchActiveAppConfigs, updateAppConfig, updateMagnetGroup } from '../services/core/apps'
import { fetchSysConfig, updateSysConfig } from '../services/core/config'

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
  const defaultDataByApp = ref({})
  const schemaByApp = ref({})
  const readonlyPathsByApp = ref({})
  const selectedAppId = ref('')
  const magnets = ref([])
  const magnetOriginalById = ref({})
  const magnetDraftById = ref({})
  const magnetVersion = ref(0)
  const magnetConflicts = ref([])
  const magnetSaving = ref(false)
  const magnetCollapsed = ref(true)
  const sysDraftData = ref({})
  const sysOriginalData = ref({})
  const sysVersion = ref(0)
  const sysReadonlyPaths = ref([])
  const needRestartToastVisible = ref(false)
  const needRestartToastMessage = ref('')
  const arrayEditorVisible = ref(false)
  const arrayEditorTitle = ref('')
  const arrayEditorItems = ref([])
  const arrayEditorPlaceholder = ref('')
  const arrayEditorItemType = ref('string')
  const arrayEditorContext = ref(null)
  const collapsedGroups = ref({})
  const touchedGroups = ref({})
  let needRestartToastTimer = null
  const showSystemAddModal = ref(false)
  const newSystemPath = ref('')
  const newSystemValue = ref('')
  const newSystemBooleanValue = ref(false)
  const newSystemSchemaType = ref('')
  const newSystemSchemaEnum = ref('')
  const newSystemSchemaMin = ref('')
  const newSystemSchemaMax = ref('')
  const newSystemSchemaMinLength = ref('')
  const newSystemSchemaMaxLength = ref('')
  const newSystemSchemaPattern = ref('')
  const newSystemSchemaItemType = ref('')
  const newSystemSchemaDescription = ref('')
  const schemaTypeOptions = ['string', 'integer', 'number', 'boolean', 'object', 'array']
  const showNewSystemTextInput = computed(() => newSystemSchemaType.value !== 'boolean')
  const newSystemValueInputType = computed(() => {
    if (newSystemSchemaType.value === 'integer' || newSystemSchemaType.value === 'number') {
      return 'number'
    }
    return 'text'
  })

  const systemRows = computed(() => {
    const schemaMap = getSysSchemaMap(sysDraftData.value || {})
    return flattenDataLeaves(sysDraftData.value || {}, new Set(sysReadonlyPaths.value || [])).map((item) => ({
      ...item,
      appId: '__system__',
      appName: t('appConfigCenter.systemTitle'),
      appVersion: '-',
      scope: 'sys',
      schemaObj: isRecord(schemaMap[item.path]) ? deepClone(schemaMap[item.path]) : null,
      type: schemaTypeFromSchema(schemaMap[item.path]) || item.type,
      rangeText: isRecord(schemaMap[item.path])
        ? buildRangeText(schemaMap[item.path], schemaTypeFromSchema(schemaMap[item.path]) || item.type)
        : '',
      description: isRecord(schemaMap[item.path]) && typeof schemaMap[item.path].description === 'string'
        ? schemaMap[item.path].description
        : '',
      needRestart: isRecord(schemaMap[item.path]) && schemaMap[item.path].need_restart === true,
    }))
  })

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
      const defaultData = defaultDataByApp.value[app.app_id] || {}
      const readonlyPaths = new Set(readonlyPathsByApp.value[app.app_id] || [])
      const appRows = flattenSchema(schema, appData, {
        appId: app.app_id,
        appName: app.name || app.app_id,
        appVersion: app.app_version || '',
      }, readonlyPaths, defaultData)
      result.push(...appRows)
    }

    return result
  })

  const appTreeRows = computed(() => {
    const tree = buildAppParamTree(rows.value)
    ensureGroupCollapsedState(tree)
    return flattenTreeForDisplay(tree, collapsedGroups.value)
  })

  const hasChanges = computed(() => collectChanges().length > 0)
  const hasMagnetChanges = computed(() => {
    for (const group of magnets.value) {
      const groupId = String(group?.group_id || '')
      if (!groupId) continue
      if (!isValueEqual(magnetOriginalById.value[groupId], magnetDraftById.value[groupId])) {
        return true
      }
    }
    return false
  })

  async function loadAllConfigs() {
    loading.value = true
    error.value = ''
    success.value = ''

    try {
      const [data, sysData] = await Promise.all([fetchActiveAppConfigs(), fetchSysConfig()])
      const items = Array.isArray(data?.items) ? data.items : []
      appItems.value = items

      const nextDraft = {}
      const nextOriginal = {}
      const nextRevision = {}
      const nextVersion = {}
      const nextDefaultData = {}
      const nextSchema = {}
      const nextReadonly = {}

      for (const item of items) {
        const appId = String(item?.app_id || '')
        if (!appId) continue

        const appData = deepClone(item?.data || {})
        nextDraft[appId] = appData
        nextOriginal[appId] = deepClone(appData)
        nextRevision[appId] = Number(item?.version || 0)
        nextVersion[appId] = String(item?.app_version || '')
        nextDefaultData[appId] = deepClone(item?.default_data || {})
        nextSchema[appId] = item?.normalized_schema || item?.schema || {}
        nextReadonly[appId] = Array.isArray(item?.readonly_paths) ? item.readonly_paths : []
      }

      draftByApp.value = nextDraft
      originalByApp.value = nextOriginal
      revisionByApp.value = nextRevision
      appVersionByApp.value = nextVersion
      defaultDataByApp.value = nextDefaultData
      schemaByApp.value = nextSchema
      readonlyPathsByApp.value = nextReadonly

      applyMagnetSnapshot(data || {})

      sysDraftData.value = deepClone(sysData?.data || {})
      sysOriginalData.value = deepClone(sysData?.data || {})
      sysVersion.value = Number(sysData?.version || 0)
      sysReadonlyPaths.value = Array.isArray(sysData?.readonly_paths) ? sysData.readonly_paths : []

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

  function applyMagnetSnapshot(snapshot) {
    const nextMagnets = Array.isArray(snapshot?.magnets) ? snapshot.magnets : []
    const nextMagnetOriginal = {}
    const nextMagnetDraft = {}
    for (const item of nextMagnets) {
      const groupId = String(item?.group_id || '')
      if (!groupId) continue
      nextMagnetOriginal[groupId] = deepClone(item?.value)
      nextMagnetDraft[groupId] = deepClone(item?.value)
    }
    magnets.value = nextMagnets
    magnetOriginalById.value = nextMagnetOriginal
    magnetDraftById.value = nextMagnetDraft
    magnetVersion.value = Number(snapshot?.magnet_version || snapshot?.magnetVersion || 0)
    magnetConflicts.value = Array.isArray(snapshot?.magnet_conflicts)
      ? snapshot.magnet_conflicts
      : (Array.isArray(snapshot?.magnetConflicts) ? snapshot.magnetConflicts : [])
    if (Array.isArray(snapshot?.readonly_paths)) {
      sysReadonlyPaths.value = snapshot.readonly_paths
    }
  }

  async function refreshMagnetsAfterSysChange() {
    const latest = await fetchSysConfig()
    applyMagnetSnapshot(latest || {})
    return latest
  }

  async function refreshAfterAppChange() {
    const latest = await fetchActiveAppConfigs()
    applyMagnetSnapshot(latest || {})

    const items = Array.isArray(latest?.items) ? latest.items : []
    const nextReadonly = { ...readonlyPathsByApp.value }
    for (const item of items) {
      const appId = String(item?.app_id || '')
      if (!appId) continue
      nextReadonly[appId] = Array.isArray(item?.readonly_paths) ? item.readonly_paths : []
    }
    readonlyPathsByApp.value = nextReadonly
  }

  function getCellValue(row) {
    if (row?.scope === 'sys') {
      return nestedGet(sysDraftData.value || {}, row.path)
    }
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

  function getArrayPreviewText(value) {
    if (!Array.isArray(value) || !value.length) {
      return t('appConfigCenter.arrayPreviewEmpty')
    }
    const previewItems = value
      .slice(0, 3)
      .map((item) => compactArrayPreviewItem(item))
      .filter((item) => item.trim() !== '')

    if (!previewItems.length) {
      return t('appConfigCenter.arrayPreviewEmpty')
    }

    let preview = previewItems.join(', ')
    if (value.length > 3) {
      preview += ', ...'
    }
    if (preview.length > 180) {
      preview = `${preview.slice(0, 177)}...`
    }
    return preview
  }

  function isArrayEditableRow(row) {
    return row?.type === 'array'
  }

  function isArrayEditableMagnet(group) {
    return String(group?.value_type || '') === 'array'
  }

  function openArrayEditorForRow(row) {
    if (!row || row.readonly || !isArrayEditableRow(row)) return
    arrayEditorContext.value = {
      kind: 'row',
      row,
    }
    arrayEditorTitle.value = t('appConfigCenter.arrayEditorTitle', {
      path: row.path || '-',
    })
    const prepared = prepareArrayEditor(Array.isArray(getCellValue(row)) ? getCellValue(row) : [], row?.schemaObj?.items)
    arrayEditorItemType.value = prepared.itemType
    arrayEditorPlaceholder.value = prepared.placeholder
    arrayEditorItems.value = prepared.items
    arrayEditorVisible.value = true
  }

  function openArrayEditorForMagnet(group) {
    if (!group || !isArrayEditableMagnet(group)) return
    arrayEditorContext.value = {
      kind: 'magnet',
      group,
    }
    arrayEditorTitle.value = t('appConfigCenter.arrayEditorTitle', {
      path: group.path || '-',
    })
    const prepared = prepareArrayEditor(Array.isArray(getMagnetValue(group)) ? getMagnetValue(group) : [], null)
    arrayEditorItemType.value = prepared.itemType
    arrayEditorPlaceholder.value = prepared.placeholder
    arrayEditorItems.value = prepared.items
    arrayEditorVisible.value = true
  }

  function closeArrayEditor() {
    arrayEditorVisible.value = false
    arrayEditorTitle.value = ''
    arrayEditorItems.value = []
    arrayEditorPlaceholder.value = ''
    arrayEditorItemType.value = 'string'
    arrayEditorContext.value = null
  }

  async function saveArrayEditor() {
    const context = arrayEditorContext.value
    if (!context) {
      closeArrayEditor()
      return
    }

    let nextValue
    try {
      nextValue = parseArrayEditorItems(arrayEditorItems.value, arrayEditorItemType.value)
    } catch (err) {
      error.value = String(err?.message || err || t('appConfigCenter.invalidValue'))
      return
    }
    if (context.kind === 'row') {
      const saved = await applyValue(context.row, nextValue)
      if (saved) {
        closeArrayEditor()
      }
      return
    }

    if (context.kind === 'magnet') {
      setMagnetValue(context.group, nextValue)
      const saved = await saveMagnetChanges(context.group)
      if (saved) {
        closeArrayEditor()
      }
    }
  }

  function addArrayEditorRow() {
    arrayEditorItems.value = [...arrayEditorItems.value, createArrayEditorRow()]
  }

  function removeArrayEditorRow(id) {
    const next = arrayEditorItems.value.filter((item) => item.id !== id)
    arrayEditorItems.value = next.length ? next : [createArrayEditorRow()]
  }

  function updateArrayEditorRow(id, text) {
    arrayEditorItems.value = arrayEditorItems.value.map((item) => (
      item.id === id
        ? { ...item, text }
        : item
    ))
  }

  async function onBooleanChange(row, checked) {
    await applyValue(row, Boolean(checked))
  }

  async function onEnumChange(row, indexText) {
    const index = Number(indexText)
    if (!Number.isInteger(index) || !Array.isArray(row.enumValues) || index < 0 || index >= row.enumValues.length) {
      return
    }
    await applyValue(row, deepClone(row.enumValues[index]))
  }

  async function onSystemEnumChange(row, indexText) {
    const enumValues = getSystemEnumValues(row)
    const index = Number(indexText)
    if (!Number.isInteger(index) || index < 0 || index >= enumValues.length) {
      return
    }
    await applyValue(row, deepClone(enumValues[index]))
  }

  async function onTextChange(row, rawText) {
    try {
      const next = parseValueByType(rawText, row.type)
      return await applyValue(row, next)
    } catch (err) {
      cellErrors.value = {
        ...cellErrors.value,
        [cellErrorKey(row)]: String(err?.message || err || t('appConfigCenter.invalidValue')),
      }
      return false
    }
  }

  async function applyValue(row, nextValue) {
    if (row.readonly) {
      error.value = t('appConfigCenter.readonlyInMagnetZone')
      return false
    }

    const currentValue = getCellValue(row)
    if (isValueEqual(currentValue, nextValue)) {
      const key = cellErrorKey(row)
      if (cellErrors.value[key]) {
        const nextErrors = { ...cellErrors.value }
        delete nextErrors[key]
        cellErrors.value = nextErrors
      }
      error.value = ''
      return true
    }

    if (row?.scope === 'sys') {
      const beforeData = deepClone(sysDraftData.value || {})
      const nextData = deepClone(sysDraftData.value || {})
      nestedSet(nextData, row.path, nextValue)
      sysDraftData.value = nextData

      const key = cellErrorKey(row)
      if (cellErrors.value[key]) {
        const nextErrors = { ...cellErrors.value }
        delete nextErrors[key]
        cellErrors.value = nextErrors
      }

      error.value = ''
      success.value = ''

      try {
        const resp = await updateSysConfig(deepClone(nextData), Number(sysVersion.value || 0))
        sysVersion.value = Number(resp?.version || sysVersion.value || 0)
        sysOriginalData.value = deepClone(nextData)
        await loadAllConfigs()
        success.value = t('appConfigCenter.autoSyncSuccess')
      } catch (err) {
        sysDraftData.value = beforeData
        error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
        return false
      }
      return true
    }

    const beforeAppData = deepClone(draftByApp.value[row.appId] || {})
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

    try {
      const resp = await updateAppConfig(row.appId, {
        version: Number(revisionByApp.value[row.appId] || 0),
        app_version: appVersionByApp.value[row.appId] || '',
        data: deepClone(appData),
      })
      revisionByApp.value = {
        ...revisionByApp.value,
        [row.appId]: Number(resp?.version || revisionByApp.value[row.appId] || 0),
      }
      originalByApp.value = {
        ...originalByApp.value,
        [row.appId]: deepClone(appData),
      }
      await loadAllConfigs()
      success.value = t('appConfigCenter.autoSyncSuccess')
      if (row.needRestart === true) {
        showNeedRestartToast(row)
      }
    } catch (err) {
      draftByApp.value = {
        ...draftByApp.value,
        [row.appId]: beforeAppData,
      }
      error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
      return false
    }
    return true
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

    const changedAppIds = [...new Set(changes.filter((item) => item.scope === 'app').map((item) => item.appId))]
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

    const hasSystemChange = changes.some((item) => item.scope === 'sys')
    if (hasSystemChange) {
      try {
        const resp = await updateSysConfig(deepClone(sysDraftData.value || {}), Number(sysVersion.value || 0))
        sysVersion.value = Number(resp?.version || sysVersion.value || 0)
        sysOriginalData.value = deepClone(sysDraftData.value || {})
      } catch (err) {
        failed.push({
          appId: '__system__',
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

  function getMagnetValue(group) {
    const groupId = String(group?.group_id || '')
    return magnetDraftById.value[groupId]
  }

  function getMagnetDisplayValue(group) {
    return valueToInlineText(getMagnetValue(group))
  }

  function getMagnetBindingsText(bindings) {
    const items = Array.isArray(bindings) ? bindings : []
    if (!items.length) return '-'

    return items
      .map((binding) => {
        if (String(binding?.kind || '') === 'sys') {
          return 'sys'
        }
        const appId = String(binding?.app_id || '')
        if (!appId) return '-'
        const app = appItems.value.find((item) => String(item?.app_id || '') === appId)
        return String(app?.name || appId)
      })
      .filter(Boolean)
      .join(', ')
  }

  function onMagnetBooleanChange(group, checked) {
    setMagnetValue(group, Boolean(checked))
  }

  function onMagnetTextChange(group, rawText) {
    try {
      const nextValue = parseValueByType(rawText, String(group?.value_type || ''))
      setMagnetValue(group, nextValue)
      return true
    } catch (err) {
      error.value = String(err?.message || err || t('appConfigCenter.invalidValue'))
      return false
    }
  }

  function setMagnetValue(group, nextValue) {
    const groupId = String(group?.group_id || '')
    if (!groupId) return
    magnetDraftById.value = {
      ...magnetDraftById.value,
      [groupId]: deepClone(nextValue),
    }
    error.value = ''
    success.value = ''
  }

  async function saveMagnetChanges(group) {
    const groupId = String(group?.group_id || '')
    if (!groupId) return false
    if (isValueEqual(magnetOriginalById.value[groupId], magnetDraftById.value[groupId])) {
      error.value = ''
      return true
    }
    magnetSaving.value = true
    error.value = ''
    success.value = ''

    try {
      const resp = await updateMagnetGroup(groupId, {
        version: Number(magnetVersion.value || 0),
        value: deepClone(magnetDraftById.value[groupId]),
      })
      magnetVersion.value = Number(resp?.version || magnetVersion.value || 0)
      magnetOriginalById.value = {
        ...magnetOriginalById.value,
        [groupId]: deepClone(magnetDraftById.value[groupId]),
      }
      await loadAllConfigs()
      success.value = t('appConfigCenter.autoSyncSuccess')
    } catch (err) {
      magnetDraftById.value = {
        ...magnetDraftById.value,
        [groupId]: deepClone(magnetOriginalById.value[groupId]),
      }
      error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
      return false
    } finally {
      magnetSaving.value = false
    }
    return true
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
        scope: 'app',
        appId: row.appId,
        appName: row.appName,
        path: row.path,
        before,
        after,
      })
    }

    for (const row of systemRows.value) {
      const before = nestedGet(sysOriginalData.value || {}, row.path)
      const after = nestedGet(sysDraftData.value || {}, row.path)
      if (isValueEqual(before, after)) {
        continue
      }
      output.push({
        scope: 'sys',
        appId: row.appId,
        appName: row.appName,
        path: row.path,
        before,
        after,
      })
    }

    return output
  }

  function showNeedRestartToast(row) {
    if (needRestartToastTimer) {
      clearTimeout(needRestartToastTimer)
      needRestartToastTimer = null
    }
    needRestartToastMessage.value = t('appConfigCenter.needRestartToast', {
      appName: row?.appName || row?.appId || '-',
      path: row?.path || '-',
    })
    needRestartToastVisible.value = true
    needRestartToastTimer = window.setTimeout(() => {
      needRestartToastVisible.value = false
      needRestartToastTimer = null
    }, 3000)
  }

  function getNeedRestartText(row) {
    return row?.needRestart === true
      ? t('appConfigCenter.needRestartYes')
      : t('appConfigCenter.needRestartNo')
  }

  function goBackApps() {
    router.push('/dashboard/apps')
  }

  function setSelectedAppId(value) {
    selectedAppId.value = String(value || '')
  }

  function toggleMagnetCollapsed() {
    magnetCollapsed.value = !magnetCollapsed.value
  }

  function isGroupCollapsed(groupId) {
    return collapsedGroups.value[groupId] !== false
  }

  function toggleGroupCollapsed(groupId) {
    const key = String(groupId || '')
    if (!key) return
    collapsedGroups.value = {
      ...collapsedGroups.value,
      [key]: !isGroupCollapsed(key),
    }
    touchedGroups.value = {
      ...touchedGroups.value,
      [key]: true,
    }
  }

  function getCurrentGroupIdsByApp(appId) {
    return getAllGroupIdsByApp(appId)
  }

  function isAppCollapsed(appId) {
    const ids = getCurrentGroupIdsByApp(appId)
    if (!ids.length) return false
    return ids.every((id) => isGroupCollapsed(id))
  }

  function setGroupsCollapsedState(groupIds, collapsed) {
    if (!groupIds.length) return
    const nextCollapsed = { ...collapsedGroups.value }
    const nextTouched = { ...touchedGroups.value }
    for (const id of groupIds) {
      nextCollapsed[id] = collapsed
      nextTouched[id] = true
    }
    collapsedGroups.value = nextCollapsed
    touchedGroups.value = nextTouched
  }

  function toggleAppCollapsed(appId) {
    const groupIds = getCurrentGroupIdsByApp(String(appId || ''))
    if (!groupIds.length) return
    setGroupsCollapsedState(groupIds, !isAppCollapsed(appId))
  }

  function collapseAllGroups() {
    const groupIds = getAllGroupIds()
    setGroupsCollapsedState(groupIds, true)
  }

  function expandAllGroups() {
    const groupIds = getAllGroupIds()
    setGroupsCollapsedState(groupIds, false)
  }

  function areAllGroupsCollapsed() {
    const groupIds = getAllGroupIds()
    if (!groupIds.length) return false
    return groupIds.every((id) => isGroupCollapsed(id))
  }

  function toggleAllGroupsCollapsed() {
    if (areAllGroupsCollapsed()) {
      expandAllGroups()
      return
    }
    collapseAllGroups()
  }

  function getAllGroupIds() {
    const appGroups = buildAppParamTree(rows.value)
    return appGroups.flatMap((appGroup) => collectGroupNodes(appGroup.nodes).map((node) => node.id))
  }

  function getAllGroupIdsByApp(appId) {
    const targetAppId = String(appId || '')
    if (!targetAppId) return []
    const appGroups = buildAppParamTree(rows.value)
    const appGroup = appGroups.find((item) => item.appId === targetAppId)
    if (!appGroup) return []
    return collectGroupNodes(appGroup.nodes).map((node) => node.id)
  }

  function ensureGroupCollapsedState(appGroups) {
    const next = { ...collapsedGroups.value }
    const nextTouched = { ...touchedGroups.value }
    const defaultCollapsed = shouldDefaultCollapseGroups(selectedAppId.value, appGroups)
    let changed = false

    for (const appGroup of appGroups) {
      for (const node of collectGroupNodes(appGroup.nodes)) {
        if (!Object.prototype.hasOwnProperty.call(next, node.id)) {
          next[node.id] = defaultCollapsed
          nextTouched[node.id] = false
          changed = true
          continue
        }
        if (nextTouched[node.id] === true) {
          continue
        }
        if (next[node.id] !== defaultCollapsed) {
          next[node.id] = defaultCollapsed
          changed = true
        }
      }
    }

    if (changed) {
      collapsedGroups.value = next
      touchedGroups.value = nextTouched
    }
  }

  function openMagnetPanel() {
    magnetCollapsed.value = false
  }

  function getMagnetRowId(path) {
    const raw = String(path || '').trim()
    const safe = raw.replace(/[^a-zA-Z0-9_-]+/g, '-')
    return `magnet-row-${safe}`
  }

  async function jumpToMagnetByPath(path) {
    const targetPath = String(path || '').trim()
    if (!targetPath) return
    openMagnetPanel()
    await nextTick()
    const element = document.getElementById(getMagnetRowId(targetPath))
    if (!element) return
    element.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  function openSystemAddModal() {
    newSystemPath.value = ''
    newSystemValue.value = ''
    newSystemBooleanValue.value = false
    newSystemSchemaType.value = ''
    newSystemSchemaEnum.value = ''
    newSystemSchemaMin.value = ''
    newSystemSchemaMax.value = ''
    newSystemSchemaMinLength.value = ''
    newSystemSchemaMaxLength.value = ''
    newSystemSchemaPattern.value = ''
    newSystemSchemaItemType.value = ''
    newSystemSchemaDescription.value = ''
    showSystemAddModal.value = true
    error.value = ''
    success.value = ''
  }

  function closeSystemAddModal() {
    showSystemAddModal.value = false
  }

  function addSystemParam() {
    const path = String(newSystemPath.value || '').trim()
    if (!path) {
      error.value = t('appConfigCenter.systemPathRequired')
      return
    }
    if (path.startsWith('_')) {
      error.value = t('appConfigCenter.systemPathInvalid')
      return
    }

    const schemaValue = buildSchemaFromFields({
      type: newSystemSchemaType.value,
      enumText: newSystemSchemaEnum.value,
      minimum: newSystemSchemaMin.value,
      maximum: newSystemSchemaMax.value,
      minLength: newSystemSchemaMinLength.value,
      maxLength: newSystemSchemaMaxLength.value,
      pattern: newSystemSchemaPattern.value,
      itemType: newSystemSchemaItemType.value,
      description: newSystemSchemaDescription.value,
    })

    if (schemaValue?.__error) {
      error.value = schemaFormErrorMessage(schemaValue.__error, t)
      return
    }

    let value = null
    const raw = String(newSystemValue.value || '').trim()
    if (!raw) {
      error.value = t('appConfigCenter.systemValueRequired')
      return
    }
    try {
      if (isRecord(schemaValue) && schemaValue.type === 'boolean') {
        value = Boolean(newSystemBooleanValue.value)
      } else if (isRecord(schemaValue) && typeof schemaValue.type === 'string' && schemaValue.type) {
        value = parseValueByType(raw, schemaValue.type)
      } else {
        value = JSON.parse(raw)
      }
    } catch {
      error.value = t('appConfigCenter.invalidValue')
      return
    }

    const beforeData = deepClone(sysDraftData.value || {})
    const next = deepClone(sysDraftData.value || {})
    nestedSet(next, path, value)
    const schemaMap = getSysSchemaMap(next)
    if (schemaValue) {
      schemaMap[path] = schemaValue
    }
    setSysSchemaMap(next, schemaMap)
    sysDraftData.value = next
    showSystemAddModal.value = false
    error.value = ''
    success.value = ''

    updateSysConfig(deepClone(next), Number(sysVersion.value || 0))
      .then(async (resp) => {
        sysVersion.value = Number(resp?.version || sysVersion.value || 0)
        sysOriginalData.value = deepClone(next)
        await loadAllConfigs()
        success.value = t('appConfigCenter.autoSyncSuccess')
      })
      .catch((err) => {
        sysDraftData.value = beforeData
        error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
      })
  }

  function removeSystemParam(row) {
    if (!row || row.readonly) {
      error.value = t('appConfigCenter.readonlyInMagnetZone')
      return
    }
    const beforeData = deepClone(sysDraftData.value || {})
    const next = deepClone(sysDraftData.value || {})
    nestedDelete(next, row.path)
    const schemaMap = getSysSchemaMap(next)
    delete schemaMap[row.path]
    setSysSchemaMap(next, schemaMap)
    sysDraftData.value = next
    error.value = ''
    success.value = ''

    updateSysConfig(deepClone(next), Number(sysVersion.value || 0))
      .then(async (resp) => {
        sysVersion.value = Number(resp?.version || sysVersion.value || 0)
        sysOriginalData.value = deepClone(next)
        await loadAllConfigs()
        success.value = t('appConfigCenter.autoSyncSuccess')
      })
      .catch((err) => {
        sysDraftData.value = beforeData
        error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
      })
  }

  function confirmRemoveSystemParam(row) {
    if (!row) return
    const message = t('appConfigCenter.systemDeleteConfirm', { path: row.path || '' })
    if (!window.confirm(message)) {
      return
    }
    removeSystemParam(row)
  }

  function onSystemSchemaChange(row, field, rawValue) {
    if (!row || row.readonly) {
      error.value = t('appConfigCenter.readonlyInMagnetZone')
      return
    }

    const current = isRecord(row.schemaObj) ? deepClone(row.schemaObj) : {}
    const nextDraft = {
      type: normalizeType(current.type),
      enumText: schemaEnumToText(current.enum),
      minimum: numberToInput(current.minimum),
      maximum: numberToInput(current.maximum),
      minLength: numberToInput(current.minLength),
      maxLength: numberToInput(current.maxLength),
      pattern: typeof current.pattern === 'string' ? current.pattern : '',
      itemType: normalizeType(current?.items?.type),
      description: typeof current.description === 'string' ? current.description : '',
    }
    nextDraft[field] = rawValue

    const parsedSchema = buildSchemaFromFields(nextDraft)
    if (parsedSchema?.__error) {
      error.value = schemaFormErrorMessage(parsedSchema.__error, t)
      return
    }

    const beforeData = deepClone(sysDraftData.value || {})
    const next = deepClone(sysDraftData.value || {})
    const schemaMap = getSysSchemaMap(next)
    if (!parsedSchema) {
      delete schemaMap[row.path]
    } else {
      schemaMap[row.path] = parsedSchema
    }
    setSysSchemaMap(next, schemaMap)
    sysDraftData.value = next
    error.value = ''
    success.value = ''

    updateSysConfig(deepClone(next), Number(sysVersion.value || 0))
      .then(async (resp) => {
        sysVersion.value = Number(resp?.version || sysVersion.value || 0)
        sysOriginalData.value = deepClone(next)
        await loadAllConfigs()
        success.value = t('appConfigCenter.autoSyncSuccess')
      })
      .catch((err) => {
        sysDraftData.value = beforeData
        error.value = String(err?.message || err || t('appConfigCenter.saveFailed'))
      })
  }

  function getRowThemeClass(appId) {
    return appThemeById.value[String(appId || '')] || 'config-row-app-0'
  }

  function getSystemEnumValues(row) {
    if (Array.isArray(row?.schemaObj?.enum) && row.schemaObj.enum.length) {
      return row.schemaObj.enum
    }
    return []
  }

  function getSystemInputType(row) {
    const type = String(row?.type || '')
    if (type === 'integer' || type === 'number') {
      return 'number'
    }
    return 'text'
  }

  function getSystemValuePlaceholder(row) {
    const type = String(row?.type || '')
    if (type === 'object' || type === 'array') {
      return t('appConfigCenter.systemValueJsonPlaceholder')
    }
    return t('appConfigCenter.systemValuePlaceholder')
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
    setSelectedAppId,
    rows,
    appTreeRows,
    systemRows,
    magnets,
    magnetConflicts,
    magnetSaving,
    magnetCollapsed,
    loadAllConfigs,
    goBackApps,
    toggleMagnetCollapsed,
    openMagnetPanel,
    getMagnetRowId,
    jumpToMagnetByPath,
    getCellValue,
    getCellError,
    displayValue,
    getArrayPreviewText,
    getDefaultText,
    getRangeText,
    getDescriptionText,
    getNeedRestartText,
    getRowThemeClass,
    isArrayEditableRow,
    isArrayEditableMagnet,
    openArrayEditorForRow,
    openArrayEditorForMagnet,
    arrayEditorVisible,
    arrayEditorTitle,
    arrayEditorItems,
    arrayEditorPlaceholder,
    closeArrayEditor,
    saveArrayEditor,
    addArrayEditorRow,
    removeArrayEditorRow,
    updateArrayEditorRow,
    isGroupCollapsed,
    toggleGroupCollapsed,
    isAppCollapsed,
    toggleAppCollapsed,
    collapseAllGroups,
    expandAllGroups,
    areAllGroupsCollapsed,
    toggleAllGroupsCollapsed,
    getSystemEnumValues,
    getSystemInputType,
    getSystemValuePlaceholder,
    showSystemAddModal,
    schemaTypeOptions,
    showNewSystemTextInput,
    newSystemValueInputType,
    newSystemPath,
    newSystemValue,
    newSystemBooleanValue,
    newSystemSchemaType,
    newSystemSchemaEnum,
    newSystemSchemaMin,
    newSystemSchemaMax,
    newSystemSchemaMinLength,
    newSystemSchemaMaxLength,
    newSystemSchemaPattern,
    newSystemSchemaItemType,
    newSystemSchemaDescription,
    getMagnetValue,
    getMagnetDisplayValue,
    getMagnetBindingsText,
    onBooleanChange,
    onEnumChange,
    onSystemEnumChange,
    onTextChange,
    openSystemAddModal,
    closeSystemAddModal,
    addSystemParam,
    removeSystemParam,
    confirmRemoveSystemParam,
    onSystemSchemaChange,
    onMagnetBooleanChange,
    onMagnetTextChange,
    saveMagnetChanges,
    valueToInlineText,
    needRestartToastVisible,
    needRestartToastMessage,
  }
}

function createArrayEditorRow(text = '') {
  return {
    id: `array-item-${Math.random().toString(36).slice(2, 10)}`,
    text,
  }
}

function prepareArrayEditor(values, itemSchema) {
  const itemType = getArrayItemType(values, itemSchema)
  return {
    itemType,
    placeholder: buildArrayItemPlaceholder(itemType, itemSchema),
    items: values.length
      ? values.map((item) => createArrayEditorRow(formatArrayItemForEditor(item)))
      : [createArrayEditorRow()],
  }
}

function parseArrayEditorItems(items, itemType) {
  const values = []
  for (const item of items) {
    const text = String(item?.text || '').trim()
    if (!text) continue
    if (itemType === 'object' || itemType === 'array') {
      values.push(parseValueByType(text, itemType))
      continue
    }
    if (itemType === 'integer' || itemType === 'number' || itemType === 'boolean' || itemType === 'null') {
      values.push(parseValueByType(text, itemType))
      continue
    }
    values.push(text)
  }
  return values
}

function getArrayItemType(values, itemSchema) {
  const schemaType = normalizeType(itemSchema?.type)
  if (schemaType) return schemaType
  const sample = Array.isArray(values) ? values.find((item) => item !== null && item !== undefined) : undefined
  if (sample !== undefined) return inferValueType(sample)
  return 'string'
}

function buildArrayItemPlaceholder(itemType, itemSchema) {
  if (itemType === 'object') {
    const example = buildObjectExample(itemSchema)
    return example ? JSON.stringify(example) : '{"key":"value"}'
  }
  if (itemType === 'array') {
    return '[\"item1\", \"item2\"]'
  }
  if (itemType === 'integer') return '1'
  if (itemType === 'number') return '3.14'
  if (itemType === 'boolean') return 'true'
  if (itemType === 'null') return 'null'
  return ''
}

function buildObjectExample(schema) {
  const properties = isRecord(schema?.properties) ? schema.properties : null
  if (!properties) return null
  const result = {}
  for (const [key, value] of Object.entries(properties)) {
    const type = normalizeType(value?.type)
    if (type === 'string') {
      result[key] = key === 'topic_name' ? '/topic/name' : (key === 'prefix' ? 'uav${sys/role/id}' : `example_${key}`)
      continue
    }
    if (type === 'integer') {
      result[key] = 1
      continue
    }
    if (type === 'number') {
      result[key] = 1.0
      continue
    }
    if (type === 'boolean') {
      result[key] = true
      continue
    }
    result[key] = null
  }
  return result
}

function formatArrayItemForEditor(value) {
  if (isRecord(value) || Array.isArray(value)) {
    return JSON.stringify(value)
  }
  if (value === null || value === undefined) return ''
  return String(value)
}

function compactArrayPreviewItem(value) {
  if (isRecord(value) || Array.isArray(value)) {
    const json = JSON.stringify(value)
    return typeof json === 'string' ? json : ''
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

function groupIdForPath(appId, fullPath) {
  return `${String(appId || '')}::${String(fullPath || '')}`
}

function buildAppParamTree(rows) {
  const groupsByApp = new Map()
  const changedPrefixesByApp = new Map()

  for (const row of rows) {
    const appId = String(row?.appId || '')
    if (!appId) continue
    if (!groupsByApp.has(appId)) {
      groupsByApp.set(appId, {
        appId,
        appName: row.appName,
        appVersion: row.appVersion,
        groups: new Map(),
        roots: [],
      })
    }

    if (row.hasDefault && !isValueEqual(row.currentValue, row.defaultValue)) {
      const prefixes = changedPrefixesByApp.get(appId) || new Set()
      const parts = String(row.path || '').split('.').filter(Boolean)
      for (let index = 0; index < parts.length; index += 1) {
        prefixes.add(parts.slice(0, index + 1).join('.'))
      }
      changedPrefixesByApp.set(appId, prefixes)
    }

    const appEntry = groupsByApp.get(appId)
    const parts = String(row.path || '').split('.').filter(Boolean)
    let parentPath = ''
    let siblings = appEntry.roots

    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index]
      const fullPath = parentPath ? `${parentPath}.${part}` : part
      const isLeaf = index === parts.length - 1

      if (isLeaf) {
        siblings.push({
          id: `${groupIdForPath(appId, fullPath)}::leaf`,
          appId,
          label: part,
          fullPath,
          depth: index,
          type: 'leaf',
          children: [],
          row,
          defaultChanged: Boolean(changedPrefixesByApp.get(appId)?.has(fullPath)),
        })
        break
      }

      let group = appEntry.groups.get(fullPath)
      if (!group) {
        group = {
          id: groupIdForPath(appId, fullPath),
          appId,
          label: part,
          fullPath,
          depth: index,
          type: 'group',
          children: [],
          row: null,
          defaultChanged: false,
        }
        appEntry.groups.set(fullPath, group)
        siblings.push(group)
      }

      if (changedPrefixesByApp.get(appId)?.has(fullPath)) {
        group.defaultChanged = true
      }

      siblings = group.children
      parentPath = fullPath
    }
  }

  return Array.from(groupsByApp.values()).map((entry) => ({
    appId: entry.appId,
    appName: entry.appName,
    appVersion: entry.appVersion,
    nodes: sortTreeNodes(entry.roots),
  }))
}

function sortTreeNodes(nodes) {
  return [...nodes]
    .sort((left, right) => {
      if (left.type !== right.type) {
        return left.type === 'group' ? -1 : 1
      }
      return String(left.label || '').localeCompare(String(right.label || ''))
    })
    .map((node) => {
      if (node.type !== 'group') return node
      return {
        ...node,
        children: sortTreeNodes(node.children || []),
      }
    })
}

function flattenTreeForDisplay(appGroups, collapsedMap) {
  const output = []

  for (const appGroup of appGroups) {
    output.push({
      type: 'app-title',
      id: `app-title:${appGroup.appId}`,
      appId: appGroup.appId,
      appName: appGroup.appName,
      appVersion: appGroup.appVersion,
    })
    appendTreeNodes(output, appGroup.nodes, collapsedMap)
  }

  return output
}

function appendTreeNodes(output, nodes, collapsedMap) {
  for (const node of nodes) {
    output.push(node)
    if (node.type !== 'group') continue
    const collapsed = collapsedMap[node.id] !== false
    if (!collapsed) {
      appendTreeNodes(output, node.children || [], collapsedMap)
    }
  }
}

function shouldDefaultCollapseGroups(selectedAppId, appGroups) {
  if (selectedAppId) return false
  return appGroups.length > 1
}

function collectGroupNodes(nodes, output = []) {
  for (const node of nodes) {
    if (node.type !== 'group') continue
    output.push(node)
    collectGroupNodes(node.children || [], output)
  }
  return output
}

function flattenSchema(schema, data, appInfo, readonlyPaths, defaultData, parentPath = '') {
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
      rows.push(...flattenSchema(childSchema, data, appInfo, readonlyPaths, defaultData, childPath))
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
    schemaObj: deepClone(schema),
    enumValues,
    rangeText,
    description: typeof schema.description === 'string' ? schema.description : '',
    defaultValue: nestedGet(defaultData, parentPath),
    hasDefault: hasNestedPath(defaultData, parentPath),
    currentValue: nestedGet(data, parentPath),
    needRestart: schema.need_restart === true,
    readonly: readonlyPaths.has(parentPath),
  })

  return rows
}

function flattenDataLeaves(data, readonlyPaths, parentPath = '') {
  if (!isRecord(data)) {
    if (!parentPath || String(parentPath).startsWith('_')) {
      return []
    }
    return [
      {
        path: parentPath,
        value: data,
        type: inferValueType(data),
        readonly: readonlyPaths.has(parentPath),
      },
    ]
  }

  const rows = []
  for (const [key, child] of Object.entries(data)) {
    if (String(key).startsWith('_')) {
      continue
    }
    const childPath = parentPath ? `${parentPath}.${key}` : key
    if (isRecord(child)) {
      rows.push(...flattenDataLeaves(child, readonlyPaths, childPath))
      continue
    }
    rows.push({
      path: childPath,
      value: child,
      type: inferValueType(child),
      readonly: readonlyPaths.has(childPath),
    })
  }
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

function schemaTypeFromSchema(schema) {
  if (!isRecord(schema)) return ''
  return normalizeType(schema.type)
}

function schemaEnumToText(values) {
  if (!Array.isArray(values) || !values.length) return ''
  return values.map((item) => valueToInlineText(item)).join(', ')
}

function numberToInput(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ''
  return String(value)
}

function parseNumberInput(raw, integerOnly) {
  const text = String(raw ?? '').trim()
  if (!text) return null
  const value = Number(text)
  if (!Number.isFinite(value)) {
    return { __error: 'number' }
  }
  if (integerOnly && !Number.isInteger(value)) {
    return { __error: 'integer' }
  }
  return value
}

function buildSchemaFromFields(fields) {
  const type = normalizeType(fields?.type)
  if (!type) return null

  const schema = { type }

  const enumText = String(fields?.enumText || '').trim()
  if (enumText) {
    const rawParts = enumText.split(',').map((item) => item.trim()).filter(Boolean)
    try {
      schema.enum = rawParts.map((item) => parseSchemaEnumValue(item, type))
    } catch {
      return { __error: 'schema enum invalid' }
    }
  }

  if (type === 'integer' || type === 'number') {
    const minValue = parseNumberInput(fields?.minimum, type === 'integer')
    if (isRecord(minValue) && minValue.__error) {
      return { __error: 'schema minimum invalid' }
    }
    if (minValue !== null) {
      schema.minimum = minValue
    }

    const maxValue = parseNumberInput(fields?.maximum, type === 'integer')
    if (isRecord(maxValue) && maxValue.__error) {
      return { __error: 'schema maximum invalid' }
    }
    if (maxValue !== null) {
      schema.maximum = maxValue
    }
  }

  if (type === 'string') {
    const minLength = parseNumberInput(fields?.minLength, true)
    if (isRecord(minLength) && minLength.__error) {
      return { __error: 'schema minLength invalid' }
    }
    if (minLength !== null) {
      schema.minLength = minLength
    }

    const maxLength = parseNumberInput(fields?.maxLength, true)
    if (isRecord(maxLength) && maxLength.__error) {
      return { __error: 'schema maxLength invalid' }
    }
    if (maxLength !== null) {
      schema.maxLength = maxLength
    }

    const pattern = String(fields?.pattern || '').trim()
    if (pattern) {
      schema.pattern = pattern
    }
  }

  if (type === 'array') {
    const itemType = normalizeType(fields?.itemType)
    if (itemType) {
      schema.items = { type: itemType }
    }
  }

  const description = String(fields?.description || '').trim()
  if (description) {
    schema.description = description
  }

  return schema
}

function parseSchemaEnumValue(text, type) {
  if (type === 'string') {
    return text
  }
  return parseValueByType(text, type)
}

function schemaFormErrorMessage(code, t) {
  if (code === 'schema enum invalid') {
    return t('appConfigCenter.schemaEnumInvalid')
  }
  if (code === 'schema minimum invalid') {
    return t('appConfigCenter.schemaMinInvalid')
  }
  if (code === 'schema maximum invalid') {
    return t('appConfigCenter.schemaMaxInvalid')
  }
  if (code === 'schema minLength invalid') {
    return t('appConfigCenter.schemaMinLengthInvalid')
  }
  if (code === 'schema maxLength invalid') {
    return t('appConfigCenter.schemaMaxLengthInvalid')
  }
  return t('appConfigCenter.systemSchemaInvalid')
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

function hasNestedPath(data, dottedPath) {
  if (!dottedPath) return false
  const segments = String(dottedPath).split('.')
  let cursor = data
  for (const segment of segments) {
    if (!isRecord(cursor) || !(segment in cursor)) {
      return false
    }
    cursor = cursor[segment]
  }
  return true
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

function nestedDelete(data, dottedPath) {
  const segments = String(dottedPath || '').split('.').filter(Boolean)
  if (!segments.length) {
    return
  }

  const stack = []
  let cursor = data
  for (let index = 0; index < segments.length - 1; index += 1) {
    const key = segments[index]
    if (!isRecord(cursor[key])) {
      return
    }
    stack.push([cursor, key])
    cursor = cursor[key]
  }

  delete cursor[segments[segments.length - 1]]

  for (let index = stack.length - 1; index >= 0; index -= 1) {
    const [parent, key] = stack[index]
    if (isRecord(parent[key]) && Object.keys(parent[key]).length === 0) {
      delete parent[key]
    }
  }
}

function flattenLeafPaths(data, parentPath = '') {
  if (!isRecord(data)) {
    if (!parentPath || parentPath.startsWith('_')) {
      return []
    }
    return [parentPath]
  }

  const paths = []
  for (const [key, value] of Object.entries(data)) {
    if (String(key).startsWith('_')) {
      continue
    }
    const nextPath = parentPath ? `${parentPath}.${key}` : String(key)
    if (isRecord(value)) {
      paths.push(...flattenLeafPaths(value, nextPath))
      continue
    }
    paths.push(nextPath)
  }
  return paths
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
  return `${row.scope || 'app'}:${row.appId}:${row.path}`
}

function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function isInteger(value) {
  return Number.isInteger(value)
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

function getSysSchemaMap(data) {
  if (!isRecord(data)) {
    return {}
  }
  const raw = data._sys_schema
  if (!isRecord(raw)) {
    return {}
  }
  const output = {}
  for (const [key, value] of Object.entries(raw)) {
    if (!isRecord(value)) {
      continue
    }
    output[String(key)] = deepClone(value)
  }
  return output
}

function setSysSchemaMap(data, schemaMap) {
  if (!isRecord(data)) {
    return
  }
  if (!isRecord(schemaMap) || Object.keys(schemaMap).length === 0) {
    delete data._sys_schema
    return
  }
  data._sys_schema = deepClone(schemaMap)
}
