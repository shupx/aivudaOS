import assert from 'node:assert/strict'
import test from 'node:test'
import { appDomainRows } from '../aivudaos/resources/ui/src/services/core/rosDomains.js'

test('only declared or configured domains appear, including zero and explicit inheritance', () => {
  const apps = [
    { app_id: 'a', data: { apriltag: { ros_domain_id: 0 }, ros: { domain_id: 5 } } },
    { app_id: 'b', data: { ros: { domain_id: -1 }, camera: { domain_id: 11 } } },
    { app_id: 'nomachine_arm64', data: { network: { domain: 'host.example' } } },
    { app_id: 'd', data: { ROS_DOMAIN_ID: '244' } },
  ]
  assert.deepEqual(appDomainRows(apps, 17).map(r => [r.appId, r.path, r.domain, r.source]), [
    ['a', 'apriltag.ros_domain_id', 0, 'override'], ['a', 'ros.domain_id', 5, 'override'],
    ['b', 'camera.domain_id', 11, 'override'], ['b', 'ros.domain_id', 17, 'inherited'],
    ['d', 'ROS_DOMAIN_ID', null, 'invalid'],
  ])
})

test('new packages can supply fields through schema, package defaults, arrays and environment entries', () => {
  const app = {
    app_id: 'future', data: { lanes: [{ domainId: 4 }], env: [{ name: 'ROS_DOMAIN_ID', value: '12' }] },
    default_data: { custom: { domain: 9 }, profiles: [{ domain_id: 0 }] },
    schema: { properties: {
      alias: { type: 'integer', description: 'ROS 2 domain ID for discovery', default: 7 },
      selector: { type: 'integer', 'x-ros-domain': true },
      enabled: { type: 'boolean', description: 'Enable ROS domain ID filtering' },
    } },
  }
  assert.deepEqual(appDomainRows([app], 2).map(r => [r.path, r.domain, r.source]), [
    ['alias', 7, 'packageDefault'], ['custom.domain', 9, 'packageDefault'],
    ['env.0.value', 12, 'override'], ['lanes.0.domainId', 4, 'override'], ['profiles.0.domain_id', 0, 'packageDefault'], ['selector', 2, 'inherited'],
  ])
})
