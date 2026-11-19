export async function copyText(text) {
  const value = String(text ?? '')
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Fallback to execCommand below for HTTP or legacy WebView contexts.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-9999px'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  let copied = false
  try {
    copied = Boolean(document.execCommand && document.execCommand('copy'))
  } finally {
    document.body.removeChild(textarea)
  }

  if (!copied) {
    throw new Error('Copy failed')
  }
}
