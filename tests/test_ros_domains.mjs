import assert from 'node:assert/strict'
import test from 'node:test'
import { appDomainRows } from '../aivudaos/resources/ui/src/services/core/rosDomains.js'

test('show every configured ROS domain and distinguish inherited, zero and invalid values', () => {
  const apps = [
    { app_id: 'a', data: { apriltag: { ros_domain_id: 0 }, ros: { domain_id: 5 } } },
    { app_id: 'b', data: { ros: { domain_id: -1 }, camera: { domain_id: 11 } } },
    { app_id: 'c', data: {} },
    { app_id: 'd', data: { ROS_DOMAIN_ID: '244' } },
  ]
  const rows = appDomainRows(apps, 17)
  assert.deepEqual(rows.map(r => [r.appId, r.path, r.domain, r.source]), [
    ['a', 'apriltag.ros_domain_id', 0, 'override'], ['a', 'ros.domain_id', 5, 'override'],
    ['b', 'ros.domain_id', 17, 'inherited'], ['c', '', 17, 'inherited'], ['d', 'ROS_DOMAIN_ID', null, 'invalid'],
  ])
})
