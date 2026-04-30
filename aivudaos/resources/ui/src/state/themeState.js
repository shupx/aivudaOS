import { computed, ref } from 'vue'

const STORAGE_KEY = 'aivuda_theme'
const VALID_THEME_MODES = new Set(['light', 'dark', 'system'])

function getStoredThemeMode() {
  const storedTheme = localStorage.getItem(STORAGE_KEY) || 'light'
  return VALID_THEME_MODES.has(storedTheme) ? storedTheme : 'light'
}

function getSystemDarkPreference() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export const themeMode = ref(getStoredThemeMode())
const systemPrefersDark = ref(getSystemDarkPreference())

export const isDarkMode = computed(() => {
  if (themeMode.value === 'dark') return true
  if (themeMode.value === 'system') return systemPrefersDark.value
  return false
})

let mediaQueryList = null
let mediaQueryListener = null

function applyThemeClass() {
  if (isDarkMode.value) {
    document.body.classList.add('dark-mode')
  } else {
    document.body.classList.remove('dark-mode')
  }
}

function bindSystemThemeListener() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return
  }

  mediaQueryList = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQueryListener = (event) => {
    systemPrefersDark.value = event.matches
    if (themeMode.value === 'system') {
      applyThemeClass()
    }
  }

  if (typeof mediaQueryList.addEventListener === 'function') {
    mediaQueryList.addEventListener('change', mediaQueryListener)
    return
  }

  if (typeof mediaQueryList.addListener === 'function') {
    mediaQueryList.addListener(mediaQueryListener)
  }
}

bindSystemThemeListener()
applyThemeClass()

export function setThemeMode(nextMode) {
  const normalizedMode = VALID_THEME_MODES.has(nextMode) ? nextMode : 'light'
  themeMode.value = normalizedMode
  localStorage.setItem(STORAGE_KEY, normalizedMode)
  systemPrefersDark.value = getSystemDarkPreference()
  applyThemeClass()
}

export function toggleTheme() {
  setThemeMode(isDarkMode.value ? 'light' : 'dark')
}
