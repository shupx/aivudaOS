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
    return Array.from(this.path || [])
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
