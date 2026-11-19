import { stationPanel } from '../stationPanel'

export function exportTextFile(text, filename, mimeType = 'application/json;charset=utf-8') {
  const safeName = String(filename || 'export.json').trim() || 'export.json'
  const content = String(text ?? '')

  if (stationPanel) {
    if (window.h16Station && typeof window.h16Station.saveTextFile === 'function') {
      window.h16Station.saveTextFile(safeName, content)
      return 'native'
    }
    throw new Error('Native file export is unavailable on this station build')
  }

  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = safeName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  return 'browser'
}
