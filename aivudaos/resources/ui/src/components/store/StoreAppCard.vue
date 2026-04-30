<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NAvatar, NText, NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  item: { type: Object, required: true },
})

const router = useRouter()

const title = computed(() => props.item?.manifest?.name || props.item?.app_id || '-')
const description = computed(() => props.item?.manifest?.description || '')

function goDetail() {
  const appId = String(props.item?.app_id || '')
  if (!appId) return
  router.push(`/dashboard/store/${encodeURIComponent(appId)}`)
}
</script>

<template>
  <NCard
    class="store-app-card"
    hoverable
    @click="goDetail"
    :style="{ cursor: 'pointer', display: 'flex', flexDirection: 'column' }"
    :content-style="{ padding: '16px', display: 'flex', flexDirection: 'column', flex: 1, gap: '16px' }"
  >
    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
      <div style="display: flex; align-items: center; gap: 12px; min-width: 0;">
        <NAvatar
          src="/app-default-icon.png"
          :size="40"
          style="flex-shrink: 0; background-color: #f8fafc; border: 1px solid #e2e8f0;"
        />
        <div style="min-width: 0; display: flex; flex-direction: column;">
          <NText
            strong
            style="font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
          >
            {{ title }}
          </NText>
        </div>
      </div>
      <div style="flex-shrink: 0;">
        <NTag type="info" size="small">{{ item.version || '-' }}</NTag>
      </div>
    </div>

    <div style="font-size: 13px; color: #475569; display: flex; flex-direction: column; gap: 4px; flex: 1;">
      <NText depth="3" style="font-size: 12px;">{{ item.app_id }}</NText>
      <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;">
        {{ description || t('store.noDescription') }}
      </div>
      <NText depth="3" style="font-size: 12px; margin-top: auto;">{{ t('store.updatedAt') }}: {{ item.updated_at_display || '-' }}</NText>
    </div>
  </NCard>
</template>

<style scoped>
.store-app-card {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.store-app-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.12);
}
</style>
