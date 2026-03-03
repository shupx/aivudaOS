<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

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
  <article
    class="app-card card-clickable"
    tabindex="0"
    @click="goDetail"
    @keydown.enter.prevent="goDetail"
    @keydown.space.prevent="goDetail"
  >
    <header class="app-card-header">
      <div class="app-title-wrap">
        <img class="app-icon" src="/app-default-icon.png" alt="store app icon">
        <h3>{{ title }}</h3>
      </div>
      <span class="app-version">v{{ item.version || '-' }}</span>
    </header>

    <div class="app-meta">
      <p><strong>{{ $t('store.appId') }}:</strong> {{ item.app_id }}</p>
      <p><strong>{{ $t('store.description') }}:</strong> {{ description || $t('store.noDescription') }}</p>
      <p><strong>{{ $t('store.updatedAt') }}:</strong> {{ item.updated_at || '-' }}</p>
    </div>
  </article>
</template>
