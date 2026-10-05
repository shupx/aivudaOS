import { createI18n } from 'vue-i18n'
import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'
import { ref } from 'vue'
import { readSetting, saveSetting, resolveLanguage, subscribeAppearance } from '../appearance'

export const localeMode = ref(readSetting('aivuda_ui_locale'))

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']

export function normalizeLocale(locale) {
  if (SUPPORTED_LOCALES.includes(locale)) {
    return locale
  }
  return 'en-US'
}

const i18n = createI18n({
  legacy: false,
  locale: resolveLanguage(localeMode.value),
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function setLocaleMode(mode) {
  localeMode.value = ['system', ...SUPPORTED_LOCALES].includes(mode) ? mode : 'system'
  saveSetting('aivuda_ui_locale', localeMode.value)
  i18n.global.locale.value = resolveLanguage(localeMode.value)
}
subscribeAppearance(() => {
  localeMode.value = readSetting('aivuda_ui_locale')
  i18n.global.locale.value = resolveLanguage(localeMode.value)
})

export default i18n
