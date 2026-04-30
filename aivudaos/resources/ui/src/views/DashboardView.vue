<script setup>
import { h, computed, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDashboard } from '../composables/useDashboard'
import { isDarkMode, toggleTheme } from '../state/themeState'
import {
  NLayout,
  NLayoutSider,
  NMenu,
  NLayoutContent,
  NIcon,
  NDropdown,
  NButton,
  NSpace,
  NText,
  NAvatar,
  NDivider
} from 'naive-ui'
import {
  Activity,
  Blocks,
  Settings,
  ShoppingBag,
  SlidersHorizontal,
  User,
  LogOut,
  Languages,
  Moon,
  Sun,
  ChevronLeft,
  ChevronRight
} from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()

const {
  locale,
  goStatus,
  goApps,
  goConfigs,
  goStore,
  goSystemSettings,
  doLogout,
  changeLocale,
  user,
  role,
} = useDashboard()

import { appState } from '../state/appState'

const sidebarCollapsed = computed({
  get: () => appState.sidebarCollapsed,
  set: (val) => { appState.sidebarCollapsed = val }
})

function renderIcon(icon) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed(() => [
  {
    label: t('dashboard.systemStatus'),
    key: 'status',
    icon: renderIcon(Activity),
  },
  {
    label: t('dashboard.appsMenu'),
    key: 'apps',
    icon: renderIcon(Blocks),
  },
  {
    label: t('dashboard.configCenter'),
    key: 'config',
    icon: renderIcon(Settings),
  },
  {
    label: t('dashboard.onlineStore'),
    key: 'store',
    icon: renderIcon(ShoppingBag),
  },
  {
    label: t('dashboard.systemSettings'),
    key: 'system-settings',
    icon: renderIcon(SlidersHorizontal),
  }
])

const activeKey = computed(() => {
  if (route.path.includes('/dashboard/status')) return 'status'
  if (route.path.includes('/dashboard/apps/configs')) return 'config'
  if (route.path.includes('/dashboard/apps')) return 'apps'
  if (route.path.includes('/dashboard/store')) return 'store'
  if (route.path.includes('/dashboard/settings')) return 'system-settings'
  return 'status'
})

const handleUpdateValue = (key) => {
  if (key === 'status') goStatus()
  else if (key === 'apps') goApps()
  else if (key === 'config') goConfigs()
  else if (key === 'store') goStore()
  else if (key === 'system-settings') goSystemSettings()
}

const userOptions = computed(() => [
  {
    label: t('dashboard.language'),
    key: 'language',
    icon: renderIcon(Languages),
    children: [
      {
        label: t('dashboard.languageOptionZh'),
        key: 'lang-zh-CN',
      },
      {
        label: t('dashboard.languageOptionEn'),
        key: 'lang-en-US',
      }
    ]
  },
  {
    label: isDarkMode.value ? t('common.lightMode', 'Light Mode') : t('common.darkMode', 'Dark Mode'),
    key: 'toggle-theme',
    icon: isDarkMode.value ? renderIcon(Sun) : renderIcon(Moon)
  },
  {
    type: 'divider',
    key: 'd1'
  },
  {
    label: t('dashboard.logout'),
    key: 'logout',
    icon: renderIcon(LogOut)
  }
])

const handleUserAction = (key) => {
  if (key === 'logout') {
    doLogout()
  } else if (key.startsWith('lang-')) {
    changeLocale(key.replace('lang-', ''))
  } else if (key === 'toggle-theme') {
    toggleTheme()
  }
}
</script>

<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      v-model:collapsed="sidebarCollapsed"
      show-trigger="arrow-circle"
      content-style="display: flex; flex-direction: column;"
    >
      <div style="height: 64px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
        <NText depth="1" style="font-size: 18px; font-weight: 600" v-if="!sidebarCollapsed">AivudaOS</NText>
        <NText depth="1" style="font-size: 18px; font-weight: 600" v-else>AOS</NText>
      </div>
      <NMenu
        style="flex: 1; overflow-y: auto;"
        :collapsed="sidebarCollapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleUpdateValue"
      />
      <div style="padding: 12px; flex-shrink: 0; display: flex; justify-content: center;">
        <NDropdown trigger="click" placement="top" :options="userOptions" @select="handleUserAction">
          <NButton quaternary :style="sidebarCollapsed ? 'padding: 0; width: 40px;' : 'width: 100%; justify-content: flex-start;'">
            <NSpace align="center" :size="sidebarCollapsed ? 0 : 8" :wrap="false">
              <NAvatar round size="small" :style="{ backgroundColor: isDarkMode ? '#334155' : '#f1f5f9', color: isDarkMode ? '#fff' : '#000' }">
                <NIcon><User /></NIcon>
              </NAvatar>
              <span v-if="!sidebarCollapsed" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px;">
                {{ user || 'User' }}
              </span>
            </NSpace>
          </NButton>
        </NDropdown>
      </div>
    </NLayoutSider>
    <NLayout :style="isDarkMode ? '' : 'background-color: #f4f7f9;'">
      <NLayoutContent position="absolute" style="top: 0; bottom: 0; background-color: transparent;">
        <div style="padding: 24px; min-height: 100%; box-sizing: border-box;">
          <RouterView />
        </div>
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<style scoped>
/* Removed old styles */
</style>
