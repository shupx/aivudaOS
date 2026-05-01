<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import StoreAppCard from '../components/store/StoreAppCard.vue'
import { useOnlineStorePage } from '../composables/useOnlineStorePage'
import { NCard, NSpace, NButton, NInput, NText, NAlert, NIcon, NEmpty, NDropdown } from 'naive-ui'
import { RefreshCw, Search, Send, ExternalLink, Download, ArrowUpDown } from 'lucide-vue-next'

const { t } = useI18n()
const {
  loading,
  error,
  addressError,
  savingAddress,
  storeAddress,
  searchText,
  normalizedStoreAddress,
  storeCertificateDownloadUrl,
  showAddressManualCheckHint,
  addressCertificateHintVisible,
  sortOption,
  sortDesc,
  displayItems,
  hasItems,
  load,
  saveAddress,
  openStoreCertificate,
  setSortOption,
} = useOnlineStorePage()

const sortOptions = computed(() => [
  {
    label: `${t('store.sortByUpdatedAt')}${sortOption.value === 'updated_at' ? (sortDesc.value ? ' ↓' : ' ↑') : ''}`,
    key: 'updated_at',
  },
  {
    label: `${t('store.sortByName')}${sortOption.value === 'name' ? (sortDesc.value ? ' ↓' : ' ↑') : ''}`,
    key: 'name',
  },
])
</script>

<template>
  <section>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <NText style="font-size: 20px; font-weight: 600;">{{ t('store.title') }}</NText>
      <NButton secondary size="small" :loading="loading" @click="load">
        <template #icon><NIcon><RefreshCw /></NIcon></template>
        {{ t('common.refresh') }}
      </NButton>
    </div>

    <NSpace vertical :size="16" style="margin-bottom: 24px;">
      <NCard>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          <NText depth="3" style="font-size: 13px;">{{ t('store.addressLabel') }}</NText>
          <div style="display: flex; gap: 8px;">
            <NInput
              v-model:value="storeAddress"
              :input-props="{ name: 'store-address', autocomplete: 'url' }"
              :placeholder="t('store.addressPlaceholder')"
              @keydown.enter.prevent="saveAddress"
              style="flex: 1;"
            />
            <NButton type="primary" :loading="savingAddress" @click="saveAddress">
              <template #icon><NIcon><Send /></NIcon></template>
              {{ t('common.submit') }}
            </NButton>
          </div>
          <NText depth="3" style="font-size: 13px; margin-top: 4px;">
            {{ t('store.addressConnectionHint') }}
            <a href="https://pypi.org/project/aivudaappstore/" target="_blank" rel="noopener noreferrer" style="color: #3b82f6;">https://pypi.org/project/aivudaappstore/</a>
          </NText>
          <NAlert v-if="addressError" type="error" style="margin-top: 8px;">{{ addressError }}</NAlert>

          <NAlert v-if="showAddressManualCheckHint" type="info" style="margin-top: 8px;">
            {{ t('store.addressManualCheckHint') }}
            <a :href="normalizedStoreAddress" target="_blank" rel="noopener noreferrer" style="color: #3b82f6;">
              {{ normalizedStoreAddress }} <NIcon><ExternalLink size="14"/></NIcon>
            </a>
             /
            <a :href="storeCertificateDownloadUrl" target="_blank" rel="noopener noreferrer" @click="openStoreCertificate" style="color: #3b82f6;">
              {{ t('store.addressDownloadCertificateLink') }} <NIcon><Download size="14"/></NIcon>
            </a>
          </NAlert>

          <NAlert v-if="addressCertificateHintVisible" type="warning" style="margin-top: 8px;">
            {{ t('store.addressCertificateHintPrefix') }}
            <a :href="t('systemSettings.caddyLocalCaChromeUrl')" target="_blank" rel="noopener noreferrer" style="color: #3b82f6;">
              {{ t('systemSettings.caddyLocalCaChromeUrl') }}
            </a>
            {{ t('store.addressCertificateHintMiddle') }}
            <strong>{{ t('systemSettings.caddyLocalCaTrustedCertificates') }}</strong>
            {{ t('store.addressCertificateHintImport') }}
            <strong>{{ t('systemSettings.caddyLocalCaImportAction') }}</strong>
            {{ t('store.addressCertificateHintSuffix') }}
          </NAlert>
        </div>
      </NCard>

      <NCard>
        <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
          <NInput
            v-model:value="searchText"
            :input-props="{ name: 'store-search', autocomplete: 'on' }"
            :placeholder="t('store.searchPlaceholder')"
            clearable
            style="flex: 1; min-width: 240px; max-width: 480px;"
          >
            <template #prefix>
              <NIcon><Search /></NIcon>
            </template>
          </NInput>

          <NDropdown trigger="click" :options="sortOptions" @select="setSortOption">
            <NButton quaternary circle :title="t('store.sortTooltip')">
              <template #icon><NIcon><ArrowUpDown /></NIcon></template>
            </NButton>
          </NDropdown>
        </div>
      </NCard>
    </NSpace>

    <NAlert v-if="error" type="error" style="margin-bottom: 24px;">{{ error }}</NAlert>

    <NEmpty v-if="!hasItems && !loading" :description="t('store.empty')" style="margin-top: 48px;" />

    <div class="apps-grid">
      <StoreAppCard
        v-for="item in displayItems"
        :key="`${item.app_id}:${item.version}`"
        :item="item"
      />
    </div>
  </section>
</template>
