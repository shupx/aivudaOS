<script setup>
import { useI18n } from 'vue-i18n'
import { NButton, NTag, useThemeVars } from 'naive-ui'
import { ArrowDown, Play, RotateCcw, Square, X } from 'lucide-vue-next'

defineProps({
  section: { type: Object, required: true },
  name: { type: String, default: '' },
  busy: Boolean,
  cancelPending: Boolean,
})
const emit = defineEmits(['run', 'restart', 'stop', 'cancel'])
const { t } = useI18n()
const theme = useThemeVars()
</script>

<template>
  <div v-if="section.showConnector" class="stage-connector" :title="t('apps.pipelineGroups.nextStage')">
    <ArrowDown :size="16" aria-hidden="true" />
  </div>
  <section v-if="section.group" class="app-list-stage" :data-group-id="section.group.id" :aria-label="name"
    :style="{ '--stage-line': theme.textColor3, '--stage-muted': theme.textColor2 }">
    <header class="stage-header">
      <span class="stage-number">{{ t('pipeline.groupOrder', { n: section.index + 1 }) }}</span>
      <h3>{{ name }}</h3>
      <NTag size="small" :bordered="false">{{ t(`pipeline.modes.${section.group.mode}`) }}</NTag>
      <NTag v-if="!section.group.enabled" size="small" :bordered="false">{{ t('common.disabled') }}</NTag>
      <span class="stage-count">{{ t('apps.pipelineGroups.runningCount', { running: section.group.runningCount, total: section.apps.length }) }}</span>
      <div class="stage-actions">
        <template v-if="section.status">
          <span role="status">{{ t(`pipeline.states.${section.status}`) }}</span>
          <NButton size="small" quaternary circle :disabled="cancelPending" :title="t('pipeline.cancelRun')"
            :aria-label="t('pipeline.cancelRun')" @click="emit('cancel')"><X :size="16" /></NButton>
        </template>
        <template v-else>
          <NButton size="small" quaternary circle :disabled="busy || !section.group.enabled || !section.apps.length"
            :title="t('apps.pipelineGroups.startGroup', { name })" :aria-label="t('apps.pipelineGroups.startGroup', { name })"
            @click="emit('run', section.group.id)"><Play :size="15" /></NButton>
          <NButton size="small" quaternary circle :disabled="busy || !section.group.enabled || !section.apps.length"
            :title="t('apps.pipelineGroups.restartGroup', { name })" :aria-label="t('apps.pipelineGroups.restartGroup', { name })"
            @click="emit('restart', section.group.id)"><RotateCcw :size="15" /></NButton>
          <NButton size="small" quaternary circle :disabled="busy || !section.group.enabled || !section.apps.length"
            :title="t('apps.pipelineGroups.stopGroup', { name })" :aria-label="t('apps.pipelineGroups.stopGroup', { name })"
            @click="emit('stop', section.group.id)"><Square :size="14" /></NButton>
        </template>
      </div>
    </header>
    <slot v-if="section.apps.length" />
    <p v-else class="empty-stage">{{ t('apps.pipelineGroups.emptyGroup') }}</p>
  </section>
  <section v-else-if="section.unassigned" class="unassigned-section" :aria-label="t('pipeline.unassigned')">
    <h3>{{ t('pipeline.unassigned') }}</h3>
    <slot />
  </section>
  <slot v-else />
</template>

<style scoped>
.app-list-stage { border: 1.5px dashed color-mix(in srgb, var(--stage-line) 72%, transparent); border-radius: 9px; padding: 12px; }
.app-list-stage + .app-list-stage { margin-top: 12px; }
.stage-header, .stage-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stage-header { margin-bottom: 10px; }
h3 { margin: 0; font-size: 16px; font-weight: 600; overflow-wrap: anywhere; }
.stage-number, .stage-count, .empty-stage, .stage-actions span { color: var(--stage-muted); font-size: 12px; }
.stage-number, .stage-count { font-variant-numeric: tabular-nums; }
.stage-number { border-inline-end: 1px solid var(--stage-line); padding-inline-end: 8px; }
.stage-actions { margin-inline-start: auto; gap: 2px; }
.stage-connector { height: 24px; display: flex; align-items: center; padding-inline-start: 22px; }
.empty-stage { margin: 0; }
.unassigned-section { margin-top: 18px; }
.unassigned-section h3 { margin-bottom: 10px; }
</style>
