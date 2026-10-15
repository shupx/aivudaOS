import assert from 'node:assert/strict'
import test from 'node:test'
import { reactive, nextTick } from '../aivudaos/resources/ui/node_modules/vue/index.mjs'
import { parameterHistoryKey, readParameterValueHistory, rememberParameterValue } from '../aivudaos/resources/ui/src/services/core/parameterValueHistory.js'
import { useParameterValueInput } from '../aivudaos/resources/ui/src/composables/useParameterValueInput.js'

function withStorage(callback) {
  const previous = globalThis.localStorage
  const data = new Map()
  globalThis.localStorage = {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
  }
  return Promise.resolve().then(() => callback(data)).finally(() => {
    if (previous === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previous
  })
}

test('history persists in recency order, bounds size and isolates parameters', () => withStorage(() => {
  const row = { appId: 'app-a', path: 'connection.address', type: 'string' }
  const key = parameterHistoryKey(row)
  for (let i = 0; i < 25; i++) rememberParameterValue(key, `address-${i}`)
  rememberParameterValue(key, 'address-20')
  rememberParameterValue(key, '')
  rememberParameterValue(key, 'x'.repeat(2049))
  const history = readParameterValueHistory(key)
  assert.equal(history.length, 20)
  assert.equal(history[0], 'address-20')
  assert.equal(new Set(history).size, 20)
  assert.deepEqual(readParameterValueHistory(parameterHistoryKey({ ...row, appId: 'app-b' })), [])
  assert.deepEqual(readParameterValueHistory(parameterHistoryKey({ ...row, type: 'number' })), [])
  assert.deepEqual(readParameterValueHistory(parameterHistoryKey({ ...row, scope: 'sys' })), [])
}))

test('sensitive fields and broken browser storage do not interfere with editing', () => withStorage(data => {
  for (const row of [
    { path: 'auth.password' }, { path: 'api_key' }, { path: 'auth.token' },
    { path: 'address', readonly: true }, { path: 'address', schemaObj: { writeOnly: true } },
    { path: 'address', schemaObj: { format: 'password' } },
  ]) assert.equal(parameterHistoryKey(row), '')
  rememberParameterValue('', 'sensitive')
  assert.equal(data.size, 0)
  data.set('AIVUDAOS_PARAMETER_HISTORY_V1:broken', '{')
  assert.deepEqual(readParameterValueHistory('broken'), [])
  globalThis.localStorage = {
    getItem() { throw new Error('blocked') }, setItem() { throw new Error('quota') },
  }
  assert.deepEqual(readParameterValueHistory('key'), [])
  assert.deepEqual(rememberParameterValue('key', 'valid'), ['valid'])
}))

test('only successful commits are cached; selection updates and submits the chosen value once', () => withStorage(async () => {
  const props = reactive({ historyKey: 'parameter-a', value: 'invalid', disabled: false, commit: async () => false })
  const input = useParameterValueInput(props, (_, value) => { props.value = value })
  assert.equal(await input.commitValue(), false)
  assert.deepEqual(readParameterValueHistory(props.historyKey), [])
  props.value = 'first'
  props.commit = async () => true
  await input.commitValue()
  props.value = 'second'
  await input.commitValue()
  input.onFocus()
  assert.deepEqual(input.options.value.map(option => option.value), ['second', 'first'])
  input.onInput('fir')
  assert.deepEqual(input.options.value.map(option => option.value), ['first'])
  let saves = 0
  let finish
  props.commit = () => {
    saves++
    assert.equal(props.value, 'first')
    return new Promise(resolve => { finish = resolve })
  }
  const selection = input.onSelect('first')
  await nextTick()
  const blur = input.commitValue()
  assert.equal(saves, 1)
  finish(true)
  await Promise.all([selection, blur])
  await input.commitValue()
  assert.equal(saves, 1, 'the keyup after selection must not submit a second time')
  assert.deepEqual(readParameterValueHistory(props.historyKey), ['first', 'second'])
  const reopened = useParameterValueInput(props, () => {})
  assert.equal(reopened.options.value[0].value, 'first')
  props.historyKey = 'parameter-b'
  await nextTick()
  assert.deepEqual(input.options.value, [])
}))
