import assert from 'node:assert/strict'
import test from 'node:test'
import { compareVersions, annotateStoreItems } from '../aivudaos/resources/ui/src/services/core/storeUpdates.js'
import zh from '../aivudaos/resources/ui/src/i18n/locales/zh-CN.js'
import en from '../aivudaos/resources/ui/src/i18n/locales/en-US.js'

test('numeric versions, prereleases and build metadata compare correctly', () => {
  for (const [a, b, result] of [
    ['1.10.0', '1.9.0', 1], ['1.0', '1.0.0', 0], ['v2.0.0', '1.99.99', 1],
    ['1.0.0', '1.0.0-rc.1', 1], ['1.0.0-rc.10', '1.0.0-rc.2', 1],
    ['1.0.0-alpha', '1.0.0-beta', -1], ['1.0.0-1', '1.0.0-alpha', -1],
    ['1.0.0-alpha', '1.0.0-alpha.1', -1], ['1.0.0+new', '1.0.0+old', 0],
    ['bad', '1.0.0', null], ['1.2.0', '', null],
  ]) assert.equal(compareVersions(a, b), result, `${a} vs ${b}`)
})

test('only newer versions of installed apps request updates; installation refresh clears them', () => {
  const items = ['newer', 'equal', 'older', 'missing', 'unknown'].map((app_id) => ({ app_id, version: '1.10.0' }))
  const installed = [
    { app_id: 'newer', active_version: '1.9.0' },
    { app_id: 'equal', active_version: '1.10.0' },
    { app_id: 'older', active_version: '2.0.0' },
    { app_id: 'unknown', active_version: '' },
  ]
  const annotated = annotateStoreItems(items, installed)
  assert.deepEqual(annotated.map((item) => item.installation_status), ['updateAvailable', 'installed', 'installed', 'notInstalled', 'installed'])
  assert.equal(annotated[0].installed_version, '1.9.0')
  installed[0].active_version = '1.10.0'
  assert.equal(annotateStoreItems(items, installed).filter((item) => item.installation_status === 'updateAvailable').length, 0)
  assert.equal(annotateStoreItems(items, []).every((item) => item.installation_status === 'notInstalled'), true)
})

test('all update messages exist in Chinese and English', () => {
  for (const locale of [zh, en]) for (const key of ['installed', 'updateAvailable', 'notInstalled', 'update', 'updatesCount', 'noUpdates']) assert.ok(locale.store[key])
})
