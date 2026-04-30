import { ref } from 'vue'

const storedTheme = localStorage.getItem('aivuda_theme') || 'light'
export const isDarkMode = ref(storedTheme === 'dark')

function applyThemeClass() {
  if (isDarkMode.value) {
    document.body.classList.add('dark-mode')
  } else {
    document.body.classList.remove('dark-mode')
  }
}

applyThemeClass()

export function toggleTheme() {
  isDarkMode.value = !isDarkMode.value
  localStorage.setItem('aivuda_theme', isDarkMode.value ? 'dark' : 'light')
  applyThemeClass()
}
