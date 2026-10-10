import assert from 'node:assert/strict'
import test from 'node:test'
import { createRenderer, h, nextTick, onMounted, onUpdated } from '../aivudaos/resources/ui/node_modules/vue/index.mjs'
import { useResizableConfigTable } from '../aivudaos/resources/ui/src/composables/useResizableConfigTable.js'

test('table layout stops rendering when idle and follows scroll/resize after async loading', async () => {
  const frames = new Map()
  const listeners = new Map()
  let frameId = 0
  const previousWindow = globalThis.window
  globalThis.window = {
    requestAnimationFrame(callback) { frames.set(++frameId, callback); return frameId },
    cancelAnimationFrame(id) { frames.delete(id) },
    addEventListener(name, callback) { listeners.set(name, callback) },
    removeEventListener(name) { listeners.delete(name) },
  }
  const scrollListeners = new Map()
  const wrap = {
    scrollLeft: 0,
    addEventListener(name, callback) { scrollListeners.set(name, callback) },
    removeEventListener(name) { scrollListeners.delete(name) },
  }
  const renderer = createRenderer({
    createElement: () => ({}), insert() {}, remove() {}, setElementText() {}, patchProp() {},
    createText: () => ({}), createComment: () => ({}), setText() {}, setComment() {},
    parentNode: () => null, nextSibling: () => null,
  })
  let layout
  let updates = 0
  const app = renderer.createApp({
    setup() {
      layout = useResizableConfigTable([100, 200, 300])
      onUpdated(() => { updates += 1 })
      return () => h('div', layout.resizeLineLefts.value.join(',') + ':' + layout.totalTableWidth.value)
    },
  })
  async function settle() {
    await nextTick()
    for (let iteration = 0; frames.size; iteration += 1) {
      assert.ok(iteration < 5, 'layout entered an endless animation-frame/render loop')
      const pending = [...frames.values()]
      frames.clear()
      pending.forEach(callback => callback())
      await nextTick()
    }
  }
  try {
    app.mount({})
    assert.equal(layout.tableWrapRef.value, null)
    layout.tableWrapRef.value = wrap
    const headers = [{ offsetLeft: 0, offsetWidth: 100 }, { offsetLeft: 100, offsetWidth: 200 }, { offsetLeft: 300, offsetWidth: 300 }]
    headers.forEach((header, index) => layout.setHeaderRef(index)(header))
    assert.equal(layout.setHeaderRef(0), layout.setHeaderRef(0), 'header ref callbacks stay stable')
    await settle()
    assert.deepEqual([...layout.resizeLineLefts.value], [100, 300])
    const initialUpdates = updates
    const initialLines = layout.resizeLineLefts.value
    headers.forEach((header, index) => layout.setHeaderRef(index)(header))
    await settle()
    assert.equal(updates, initialUpdates)
    assert.equal(layout.resizeLineLefts.value, initialLines)
    wrap.scrollLeft = 30
    scrollListeners.get('scroll')()
    await settle()
    assert.deepEqual([...layout.resizeLineLefts.value], [70, 270])
    headers[0].offsetWidth = 140
    headers[1].offsetLeft = 140
    layout.startColumnResize(0, { preventDefault() {}, clientX: 0 })
    listeners.get('pointermove')({ clientX: 40 })
    await settle()
    assert.equal(layout.columnWidths.value[0], 140)
    assert.deepEqual([...layout.resizeLineLefts.value], [110, 310])
    app.unmount()
    assert.equal(frames.size, 0)
    assert.equal(scrollListeners.size, 0)
    assert.equal(listeners.size, 0)
  } finally {
    globalThis.window = previousWindow
  }
})
