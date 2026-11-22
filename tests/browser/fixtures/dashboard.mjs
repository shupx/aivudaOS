import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const dist = new URL('../../../aivudaos/resources/ui/dist/', import.meta.url)

export async function dashboardPage(t, path, handleApi, timeout = 5000) {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })
  t.after(() => browser.close())
  const page = await browser.newPage()
  page.setDefaultTimeout(timeout)
  await page.addInitScript(() => {
    localStorage.setItem('aivuda_ui_locale', 'en-US')
    localStorage.setItem('aivuda_ui_token', 'test')
  })
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.pathname !== path && !url.pathname.startsWith('/assets/')) return handleApi(route, url)
    const name = url.pathname === path ? 'index.html' : url.pathname.slice(1)
    const contentType = name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html'
    return route.fulfill({ contentType, body: await readFile(new URL(name, dist)) })
  })
  await page.goto(`http://ui.test${path}`)
  return page
}
