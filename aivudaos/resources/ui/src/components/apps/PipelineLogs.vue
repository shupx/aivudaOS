<script setup>
import { useI18n } from 'vue-i18n'
defineProps({ lines: Array })
const { t } = useI18n()
</script>

<template>
  <details v-if="lines?.length" class="pipeline-log" open>
    <summary>{{ t('pipeline.operationLog') }}</summary>
    <div role="log"><div v-for="(line, i) in lines" :key="i">{{ line }}</div></div>
  </details>
</template>

<style scoped>
.pipeline-log { margin-block: 8px; }
.pipeline-log > div { max-height: 12em; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 monospace; }
</style>
