const FG_COLORS = {
  30: '#94a3b8',
  31: '#ef4444',
  32: '#22c55e',
  33: '#f59e0b',
  34: '#60a5fa',
  35: '#d946ef',
  36: '#22d3ee',
  37: '#e2e8f0',
  90: '#64748b',
  91: '#f87171',
  92: '#4ade80',
  93: '#fbbf24',
  94: '#93c5fd',
  95: '#e879f9',
  96: '#67e8f9',
  97: '#f8fafc',
}

const BG_COLORS = {
  40: '#0f172a',
  41: '#7f1d1d',
  42: '#14532d',
  43: '#78350f',
  44: '#1e3a8a',
  45: '#701a75',
  46: '#164e63',
  47: '#334155',
  100: '#1e293b',
  101: '#991b1b',
  102: '#166534',
  103: '#92400e',
  104: '#1d4ed8',
  105: '#86198f',
  106: '#155e75',
  107: '#475569',
}

function initialState() {
  return {
    fg: null,
    bg: null,
    bold: false,
    italic: false,
    underline: false,
    dim: false,
  }
}

function applyCodes(state, rawCodes) {
  const normalized = rawCodes.length ? rawCodes : [0]

  normalized.forEach((code) => {
    if (code === 0) {
      Object.assign(state, initialState())
      return
    }
    if (code === 1) {
      state.bold = true
      return
    }
    if (code === 2) {
      state.dim = true
      return
    }
    if (code === 3) {
      state.italic = true
      return
    }
    if (code === 4) {
      state.underline = true
      return
    }
    if (code === 22) {
      state.bold = false
      state.dim = false
      return
    }
    if (code === 23) {
      state.italic = false
      return
    }
    if (code === 24) {
      state.underline = false
      return
    }
    if (code === 39) {
      state.fg = null
      return
    }
    if (code === 49) {
      state.bg = null
      return
    }
    if (FG_COLORS[code]) {
      state.fg = FG_COLORS[code]
      return
    }
    if (BG_COLORS[code]) {
      state.bg = BG_COLORS[code]
    }
  })
}

function appendStyledText(target, state, text) {
  if (!text) return
  const hasStyle = state.fg || state.bg || state.bold || state.italic || state.underline || state.dim
  if (!hasStyle) {
    target.appendChild(document.createTextNode(text))
    return
  }

  const span = document.createElement('span')
  if (state.fg) span.style.color = state.fg
  if (state.bg) span.style.backgroundColor = state.bg
  if (state.bold) span.style.fontWeight = '700'
  if (state.italic) span.style.fontStyle = 'italic'
  if (state.underline) span.style.textDecoration = 'underline'
  if (state.dim) span.style.opacity = '0.72'
  span.textContent = text
  target.appendChild(span)
}

export function createAnsiRenderer(target) {
  const state = initialState()
  let pendingEscape = ''

  function reset() {
    Object.assign(state, initialState())
    pendingEscape = ''
  }

  function append(chunk) {
    if (!chunk) return

    const text = `${pendingEscape}${String(chunk)}`
    pendingEscape = ''
    let cursor = 0

    while (cursor < text.length) {
      const esc = text.indexOf('\u001b', cursor)
      if (esc < 0) {
        appendStyledText(target, state, text.slice(cursor))
        break
      }

      if (esc > cursor) {
        appendStyledText(target, state, text.slice(cursor, esc))
      }

      if (esc + 1 >= text.length) {
        pendingEscape = text.slice(esc)
        break
      }

      if (text[esc + 1] !== '[') {
        cursor = esc + 1
        continue
      }

      const end = text.indexOf('m', esc + 2)
      if (end < 0) {
        pendingEscape = text.slice(esc)
        break
      }

      const raw = text.slice(esc + 2, end)
      const codes = raw
        .split(';')
        .filter((item) => item.length > 0)
        .map((item) => Number.parseInt(item, 10))
        .filter((num) => Number.isFinite(num))

      applyCodes(state, codes)
      cursor = end + 1
    }
  }

  return {
    append,
    reset,
  }
}
