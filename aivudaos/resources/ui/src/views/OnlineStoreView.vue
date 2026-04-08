<script setup>
import { useI18n } from 'vue-i18n'
import StoreAppCard from '../components/store/StoreAppCard.vue'
import { useOnlineStorePage } from '../composables/useOnlineStorePage'

const { t } = useI18n()
const {
  loading,
  error,
  addressError,
  storeAddress,
  normalizedStoreAddress,
  showAddressManualCheckHint,
  displayItems,
  hasItems,
  load,
  saveAddress,
} = useOnlineStorePage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <div class="panel-actions panel-title-actions">
        <h2>{{ t('store.title') }}</h2>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="load">
          {{ loading ? t('common.refreshing') : t('common.refresh') }}
        </button>
      </div>
    </header>

    <article class="store-setting-panel">
      <label class="muted" for="store-address-input">{{ t('store.addressLabel') }}</label>
      <div class="panel-actions wrap">
        <input
          id="store-address-input"
          v-model="storeAddress"
          class="select-input store-address-input"
          type="text"
          :placeholder="t('store.addressPlaceholder')"
          @keydown.enter.prevent="saveAddress"
        >
      </div>
      <p class="muted">
        {{ t('store.addressConnectionHint') }}
        <a
          href="https://pypi.org/project/aivudaappstore/"
          target="_blank"
          rel="noopener noreferrer"
        >
          https://pypi.org/project/aivudaappstore/
        </a>
      </p>
      <p v-if="addressError" class="error-text">{{ addressError }}</p>
      <p v-if="showAddressManualCheckHint" class="muted">
        {{ t('store.addressManualCheckHint') }}
        <a
          :href="normalizedStoreAddress"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ normalizedStoreAddress }}
        </a>
      </p>
    </article>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!hasItems && !loading" class="empty-box">
      {{ t('store.empty') }}
    </div>

    <div class="apps-grid">
      <StoreAppCard
        v-for="item in displayItems"
        :key="`${item.app_id}:${item.version}`"
        :item="item"
      />
    </div>
  </section>
</template>
