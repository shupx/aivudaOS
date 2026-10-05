export function readSetting(key, fallback = 'system') {
  try { return localStorage.getItem(key) || fallback } catch (_) { return fallback }
}

export function saveSetting(key, value) {
  try { localStorage.setItem(key, value) } catch (_) {}
}

export function resolveLanguage(mode) {
  if (mode === 'en-US' || mode === 'zh-CN') return mode
  if (mode !== 'system') return 'en-US'
  try {
    return /^zh(?:-|_|$)/i.test(navigator.language || '') ? 'zh-CN' : 'en-US'
  } catch (_) { return 'en-US' }
}

export function resolveTheme(mode) {
  if (mode === 'light' || mode === 'dark') return mode
  if (mode !== 'system') return 'light'
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch (_) { return 'light' }
}

export function subscribeAppearance(callback) {
  window.addEventListener('storage', callback)
  window.addEventListener('languagechange', callback)
  let media
  try {
    media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', callback)
  } catch (_) {}
  return () => {
    window.removeEventListener('storage', callback)
    window.removeEventListener('languagechange', callback)
    media?.removeEventListener('change', callback)
  }
}
