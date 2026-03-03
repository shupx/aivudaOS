import { useI18n } from 'vue-i18n'

const KB = 1024
const MB = 1024 * 1024

export function useStoreDisplayFormat() {
  const { locale } = useI18n()

  function parseToDate(value) {
    if (value === null || value === undefined || value === '') return null

    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : value
    }

    const asNumber = typeof value === 'number'
      ? value
      : (typeof value === 'string' && /^\d+(\.\d+)?$/.test(value.trim()) ? Number(value) : NaN)

    if (Number.isFinite(asNumber)) {
      const timestampMs = Math.abs(asNumber) < 1e12 ? asNumber * 1000 : asNumber
      const byTs = new Date(timestampMs)
      return Number.isNaN(byTs.getTime()) ? null : byTs
    }

    const byText = new Date(String(value))
    return Number.isNaN(byText.getTime()) ? null : byText
  }

  function formatStoreUpdatedAt(value) {
    if (!value) return '-'

    const date = parseToDate(value)
    if (!date) {
      return String(value)
    }

    const currentLocale = locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
    return new Intl.DateTimeFormat(currentLocale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(date)
  }

  function formatStorePackageSize(sizeBytes) {
    const size = Number(sizeBytes || 0)
    if (!Number.isFinite(size) || size <= 0) {
      return '0 kB'
    }

    if (size < MB) {
      return `${(size / KB).toFixed(1)} kB`
    }

    return `${(size / MB).toFixed(1)} MB`
  }

  return {
    formatStoreUpdatedAt,
    formatStorePackageSize,
  }
}
