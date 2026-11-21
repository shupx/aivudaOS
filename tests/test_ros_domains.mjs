import assert from 'node:assert/strict'
import test from 'node:test'
import { appDomainRows, isDomainReadonly, parseDomainInput } from '../aivudaos/resources/ui/src/services/core/rosDomains.js'

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

test('opaque IDs stay ordinary unless explicitly marked, scoped to ROS/DDS, or numeric', () => {
  const text = { type: ['string', 'null'], description: 'Identity provider domain ID' }
  const app = { app_id: 'one', data: {
    identity: { domain_id: 'id-2' }, ros: { domain_id: 'invalid' }, camera: { domain_id: '5' }, alias: 'invalid',
  }, schema: { properties: {
    identity: { properties: { domain_id: text } }, ros: { properties: { domain_id: text } },
    camera: { properties: { domain_id: text } }, alias: { type: 'string', 'x-ros-domain': true },
  } } }
  assert.deepEqual(appDomainRows([app], 1).map(r => [r.path, r.source]), [
    ['alias', 'invalid'], ['camera.domain_id', 'override'], ['ros.domain_id', 'invalid'],
  ])
})

test('a domain row respects its own binding and all ancestor bindings, not similarly named paths', () => {
  const [row] = appDomainRows([{ app_id: 'a', data: { lanes: [{ domain_id: 2 }] } }], 0)
  for (const path of ['lanes', 'lanes.0', 'lanes.0.domain_id']) assert.equal(isDomainReadonly(row, [path]), true)
  assert.equal(isDomainReadonly(row, ['lane', 'lanes.1']), false)
  assert.equal(isDomainReadonly({ ...row, readonly: true }, []), true)
})

test('nullable domain strings save as strings and validate against string enum values', () => {
  for (const types of [['string', 'null'], ['null', 'string']]) {
    const [row] = appDomainRows([{ app_id: 'a', data: { ros_domain_id: '7' }, schema: { properties: {
      ros_domain_id: { type: types, enum: ['7', '8', null] },
    } } }], 0)
    const parsed = parseDomainInput(row, '8')
    assert.equal(parsed.valid, true)
    assert.equal(parsed.value, '8')
    assert.equal(parseDomainInput(row, '9').valid, false)
  }
})

test('explicit null inherits even with a package default; clearing a nullable field saves null', () => {
  for (const type of ['integer', 'string']) {
    const schema = { properties: { ros_domain_id: { type: ['null', type] } } }
    const [row] = appDomainRows([{ app_id: 'a', data: { ros_domain_id: null }, default_data: { ros_domain_id: 5 }, schema }], 19)
    assert.equal(row.value, null)
    assert.equal(row.source, 'inherited')
    assert.equal(row.domain, 19)
    assert.equal(parseDomainInput(row, '').valid, true)
    assert.equal(parseDomainInput(row, '').value, null)
    assert.equal(parseDomainInput(row, '8').value, type === 'integer' ? 8 : '8')
    assert.equal(parseDomainInput({ ...row, schemaObj: { type } }, '').valid, false)
    assert.equal(parseDomainInput({ ...row, scope: 'sys' }, null).valid, false)
    assert.equal(parseDomainInput({ ...row, schemaObj: { type: ['null', type], enum: ['8'] } }, null).valid, false)
  }
})

test('mixed enum selections preserve the JSON type of each option', () => {
  const row = { type: 'string', schemaObj: { type: ['string', 'integer', 'null'], enum: [8, '8', null] } }
  for (const selected of [8, '8', null]) {
    assert.equal(parseDomainInput(row, selected).valid, true)
    assert.equal(parseDomainInput(row, selected).value, selected)
  }
})

test('version-zero API data is copied from package defaults, not a saved override', () => {
  const app = { app_id: 'a', data: { domain_id: 0 }, default_data: { domain_id: 0 } }
  assert.equal(appDomainRows([{ ...app, version: 0 }], 1)[0].source, 'packageDefault')
  assert.equal(appDomainRows([{ ...app, version: 1 }], 1)[0].source, 'override')
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
