<script setup>
import { useI18n } from 'vue-i18n'
import StoreAppCard from '../components/store/StoreAppCard.vue'
import { useOnlineStorePage } from '../composables/useOnlineStorePage'

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
  displayItems,
  hasItems,
  load,
  saveAddress,
  openStoreCertificate,
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
      <div class="panel-actions wrap store-address-row">
        <input
          id="store-address-input"
          v-model="storeAddress"
          class="select-input store-address-input"
          type="text"
          :placeholder="t('store.addressPlaceholder')"
          @keydown.enter.prevent="saveAddress"
        >
        <button
          type="button"
          class="btn primary store-address-confirm-btn"
          :disabled="savingAddress"
          @click="saveAddress"
        >
          {{ savingAddress ? t('common.processing') : t('common.submit') }}
        </button>
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
        <span> / </span>
        <a
          :href="storeCertificateDownloadUrl"
          target="_blank"
          rel="noopener noreferrer"
          @click="openStoreCertificate"
        >
          {{ t('store.addressDownloadCertificateLink') }}
        </a>
      </p>
      <p v-if="addressCertificateHintVisible" class="muted">
        {{ t('store.addressCertificateHintPrefix') }}
        <a :href="t('systemSettings.caddyLocalCaChromeUrl')">
          {{ t('systemSettings.caddyLocalCaChromeUrl') }}
        </a>
        {{ t('store.addressCertificateHintMiddle') }}
        <strong>{{ t('systemSettings.caddyLocalCaTrustedCertificates') }}</strong>
        {{ t('store.addressCertificateHintImport') }}
        <strong>{{ t('systemSettings.caddyLocalCaImportAction') }}</strong>
        {{ t('store.addressCertificateHintSuffix') }}
      </p>
    </article>

    <article class="store-setting-panel">
      <div class="panel-actions wrap store-inline-form-row">
        <div class="search-input-shell store-search-input-shell">
          <input
            id="store-search-input"
            v-model="searchText"
            class="select-input search-input-with-clear"
            type="text"
            :placeholder="t('store.searchPlaceholder')"
          >
          <button v-if="String(searchText || '')" type="button" class="search-clear-btn" @click="searchText = ''">x</button>
        </div>
      </div>
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
