<script setup>
import { h, computed, ref } from 'vue'
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
  NAvatar
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
  goStatus,
  goApps,
  goConfigs,
  goStore,
  goSystemSettings,
  sidebarMode,
  collapseSidebar,
  expandSidebar,
  doLogout,
  changeLocale,
  user,
} = useDashboard()

const sidebarCollapsed = computed(() => sidebarMode.value !== 'expanded')
const isSidebarExpanded = computed(() => sidebarMode.value === 'expanded')
const isSidebarIconOnly = computed(() => sidebarMode.value === 'icon')
const isSidebarHidden = computed(() => sidebarMode.value === 'hidden')
const isSidebarDragging = computed(() => Boolean(sidebarDragState.value))
const siderCollapsedWidth = computed(() => (isSidebarHidden.value ? 0 : 64))
const sidebarDragState = ref(null)

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

function onSidebarDragStart(event) {
  if (event.pointerType === 'mouse' && event.buttons !== 1) return
  event.currentTarget?.setPointerCapture?.(event.pointerId)
  sidebarDragState.value = {
    x: event.clientX,
    lastActionX: event.clientX,
    pointerId: event.pointerId,
  }
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
}

function onSidebarDragMove(event) {
  if (!sidebarDragState.value) return
  const deltaX = event.clientX - sidebarDragState.value.lastActionX

  if (deltaX <= -36) {
    collapseSidebar()
    sidebarDragState.value.lastActionX = event.clientX
  } else if (deltaX >= 36) {
    expandSidebar()
    sidebarDragState.value.lastActionX = event.clientX
  }
}

function onSidebarDragEnd(event) {
  if (!sidebarDragState.value) return
  if (event?.currentTarget && sidebarDragState.value.pointerId != null) {
    event.currentTarget.releasePointerCapture?.(sidebarDragState.value.pointerId)
  }
  sidebarDragState.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
</script>

<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider
      bordered
      collapse-mode="width"
      :collapsed="sidebarCollapsed"
      :collapsed-width="siderCollapsedWidth"
      :width="240"
      :show-trigger="false"
      content-style="display: flex; flex-direction: column; position: relative; overflow-x: hidden;"
    >
      <div style="height: 64px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
        <NText depth="1" style="font-size: 18px; font-weight: 600" v-if="isSidebarExpanded">AivudaOS</NText>
        <NText depth="1" style="font-size: 18px; font-weight: 600" v-else-if="isSidebarIconOnly">AOS</NText>
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
      <div v-if="!isSidebarHidden" style="padding: 12px; flex-shrink: 0; display: flex; justify-content: center;">
        <NDropdown trigger="click" placement="top" :options="userOptions" @select="handleUserAction">
          <NButton quaternary :style="isSidebarExpanded ? 'width: 100%; justify-content: flex-start;' : 'padding: 0; width: 40px;'">
            <NSpace align="center" :size="isSidebarExpanded ? 8 : 0" :wrap="false">
              <NAvatar round size="small" :style="{ backgroundColor: isDarkMode ? '#334155' : '#f1f5f9', color: isDarkMode ? '#fff' : '#000' }">
                <NIcon><User /></NIcon>
              </NAvatar>
              <span v-if="isSidebarExpanded" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px;">
                {{ user || 'User' }}
              </span>
            </NSpace>
          </NButton>
        </NDropdown>
      </div>
      <div
        v-if="isSidebarIconOnly"
        class="dashboard-sidebar-hidden-toggle"
        :class="{ 'is-dark': isDarkMode }"
      >
        <NButton
          quaternary
          size="tiny"
          class="dashboard-sidebar-hidden-toggle-btn"
          title="Collapse Sidebar"
          @click="collapseSidebar"
        >
          <template #icon>
            <NIcon>
              <ChevronLeft />
            </NIcon>
          </template>
        </NButton>
      </div>
      <div
        class="dashboard-sidebar-drag-rail"
        :class="{ 'is-dark': isDarkMode, 'is-dragging': isSidebarDragging }"
        title="Drag left or right to collapse or expand sidebar"
        @pointerdown="onSidebarDragStart"
        @pointermove="onSidebarDragMove"
        @pointerup="onSidebarDragEnd"
        @pointercancel="onSidebarDragEnd"
      />
    </NLayoutSider>
    <NLayout :style="isDarkMode ? '' : 'background-color: #f4f7f9;'">
      <NLayoutContent position="absolute" style="top: 0; bottom: 0; background-color: transparent;">
        <div style="padding: 24px; min-height: 100%; box-sizing: border-box; position: relative;">
          <div
            v-if="isSidebarHidden"
            class="dashboard-sidebar-hidden-toggle"
            :class="{ 'is-dark': isDarkMode }"
          >
            <NButton
              quaternary
              size="tiny"
              class="dashboard-sidebar-hidden-toggle-btn"
              title="Expand Sidebar"
              @click="expandSidebar"
            >
              <template #icon>
                <NIcon>
                  <ChevronRight />
                </NIcon>
              </template>
            </NButton>
          </div>
          <RouterView />
        </div>
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<style scoped>
.dashboard-sidebar-hidden-toggle {
  position: fixed;
  top: 50%;
  left: 4px;
  transform: translateY(-50%);
  z-index: 40;
}

.dashboard-sidebar-hidden-toggle-btn {
  width: 18px;
  min-width: 18px;
  height: 36px;
  padding: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: rgba(71, 85, 105, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.22);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(10px);
  transition: transform 0.18s ease, background-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.dashboard-sidebar-hidden-toggle-btn:hover {
  transform: translateX(1px);
  background: rgba(255, 255, 255, 0.92);
  color: #0f172a;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
}

.dashboard-sidebar-hidden-toggle.is-dark .dashboard-sidebar-hidden-toggle-btn {
  background: rgba(15, 23, 42, 0.72);
  color: rgba(226, 232, 240, 0.86);
  border-color: rgba(148, 163, 184, 0.2);
}

.dashboard-sidebar-hidden-toggle.is-dark .dashboard-sidebar-hidden-toggle-btn:hover {
  background: rgba(15, 23, 42, 0.9);
  color: #f8fafc;
  box-shadow: 0 12px 28px rgba(2, 6, 23, 0.3);
}

.dashboard-sidebar-drag-rail {
  position: absolute;
  top: 10px;
  right: 0;
  bottom: 10px;
  width: 6px;
  cursor: ew-resize;
  z-index: 5;
}

.dashboard-sidebar-drag-rail::before {
  content: none;
}
</style>
