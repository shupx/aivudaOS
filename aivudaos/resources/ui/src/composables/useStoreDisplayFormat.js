const KB = 1024
const MB = 1024 * 1024

export function useStoreDisplayFormat() {
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

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hour = String(date.getHours()).padStart(2, '0')
    const minute = String(date.getMinutes()).padStart(2, '0')
    const second = String(date.getSeconds()).padStart(2, '0')
    return `${year}.${month}.${day} ${hour}:${minute}:${second}`
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
