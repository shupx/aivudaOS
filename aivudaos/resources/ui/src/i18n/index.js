import { createI18n } from 'vue-i18n'
import { LOCALE_KEY } from '../state/preferenceKeys'
import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']

export function normalizeLocale(locale) {
  if (SUPPORTED_LOCALES.includes(locale)) {
    return locale
  }
  return 'en-US'
}

const i18n = createI18n({
  legacy: false,
  locale: normalizeLocale(localStorage.getItem(LOCALE_KEY) || 'en-US'),
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export default i18n
