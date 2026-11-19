import './h16-panel.css'
import { APPSTORE_BASE_URL_STORAGE_KEY, LOCALE_KEY } from './state/preferenceKeys'

const { store, locale } = window.h16Settings || {}
if (store && localStorage.getItem('h16_store_setting') !== store) {
  localStorage.setItem('h16_store_setting', store)
  localStorage.setItem(APPSTORE_BASE_URL_STORAGE_KEY, store)
}
if (locale && !localStorage.getItem(LOCALE_KEY)) localStorage.setItem(LOCALE_KEY, locale)

document.documentElement.classList.add('h16')

// Chromium 52 exposes the event propagation path under its original name.
if (!Event.prototype.composedPath) {
  Event.prototype.composedPath = function () {
    if (this.path && this.path.length) return Array.from(this.path)
    const path = []
    let node = this.target
    while (node) {
      path.push(node)
      node = node.parentNode || node.host || null
    }
    if (path.indexOf(document) === -1 && this.target !== window) path.push(document)
    if (path.indexOf(window) === -1) path.push(window)
    return path
  }
}

// Native input events still fire on Chromium 52, but its global constructor is missing.
// Keep ordinary events distinct so compositionstart/end can track IME input.
if (typeof window.InputEvent === 'undefined') {
  window.InputEvent = class InputEvent extends Event {
    constructor(type, init = {}) {
      super(type, init)
      this.data = init.data == null ? null : init.data
      this.inputType = init.inputType || ''
      this.isComposing = Boolean(init.isComposing)
    }
  }
}

// Chromium 52 lacks Blob/File.prototype.text and arrayBuffer (added in Chrome 76).
if (typeof Blob !== 'undefined' && !Blob.prototype.text) {
  Blob.prototype.text = function () {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error || new Error('Failed to read file'))
      reader.readAsText(this)
    })
  }
}

if (typeof Blob !== 'undefined' && !Blob.prototype.arrayBuffer) {
  Blob.prototype.arrayBuffer = function () {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = () => reject(reader.error || new Error('Failed to read file'))
      reader.readAsArrayBuffer(this)
    })
  }
}
