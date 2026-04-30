<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN, enUS, dateEnUS, darkTheme } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { isDarkMode } from './state/themeState'

const { locale } = useI18n()

const naiveLocale = computed(() => {
  return locale.value === 'zh-CN' ? zhCN : enUS
})

const naiveDateLocale = computed(() => {
  return locale.value === 'zh-CN' ? dateZhCN : dateEnUS
})

const themeOverrides = computed(() => {
  const overrides = {
    common: {
      primaryColor: '#2563eb',
      primaryColorHover: '#3b82f6',
      primaryColorPressed: '#1d4ed8',
      primaryColorSuppl: '#3b82f6',
      borderRadius: '10px',
      borderRadiusSmall: '8px',
      boxShadow1: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
      boxShadow2: '0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)',
      boxShadow3: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    },
    Card: {
      borderRadius: '16px',
      boxShadow: '0 4px 12px 0 rgba(0, 0, 0, 0.05)',
    },
    Button: {
      borderRadiusMedium: '10px',
      borderRadiusLarge: '12px',
      borderRadiusSmall: '8px',
      fontWeight: '500',
    },
    Input: {
      borderRadius: '10px',
    },
    Select: {
      borderRadius: '10px',
    },
  }

  if (!isDarkMode.value) {
    overrides.common.bodyColor = '#f4f7f9'
    overrides.common.cardColor = '#ffffff'
    overrides.Card.borderColor = '#e2e8f0'
    overrides.Layout = {
      color: '#f4f7f9',
      headerColor: '#ffffff',
      siderColor: '#ffffff',
    }
  }

  return overrides
})

const currentTheme = computed(() => isDarkMode.value ? darkTheme : null)
</script>

<template>
  <NConfigProvider :theme="currentTheme" :locale="naiveLocale" :date-locale="naiveDateLocale" :theme-overrides="themeOverrides">
    <NDialogProvider>
      <NMessageProvider>
        <RouterView />
      </NMessageProvider>
    </NDialogProvider>
  </NConfigProvider>
</template>

