<script setup>
import { provide, reactive, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueFlow } from '@vue-flow/core'
// Keep both the graph runtime and its styles behind the Apps tab's async import.
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { NButton, NPopconfirm, NSpin, useThemeVars } from 'naive-ui'
import { ChevronRight, LayoutGrid, Play, Plus, Settings, Square, X } from 'lucide-vue-next'
import { useStartupPipeline } from '../../composables/useStartupPipeline'
import PipelineAppNode from './PipelineAppNode.vue'
import PipelineGroupNode from './PipelineGroupNode.vue'
import PipelineNodeConfigDrawer from './PipelineNodeConfigDrawer.vue'
import PipelineSettingsDrawer from './PipelineSettingsDrawer.vue'

const props = defineProps({ apps: { type: Array, required: true }, operationRevision: { type: Number, default: 0 } })
const emit = defineEmits(['saved', 'operation-finished'])
const { t } = useI18n(), theme = useThemeVars()
const ui = reactive(useStartupPipeline(toRef(props, 'apps'), toRef(props, 'operationRevision'), {
  onSaved: config => emit('saved', config), onFinished: () => emit('operation-finished'),
}))
provide('pipelineEditor', ui)
defineExpose({ flush: ui.flush })
</script>

<template>
  <section class="pipeline" :aria-label="t('pipeline.title')" :style="{
    '--surface': theme.cardColor, '--paper': theme.bodyColor, '--line': theme.borderColor,
    '--ink': theme.textColor1, '--muted': theme.textColor2, '--accent': theme.primaryColor,
    '--ok': theme.successColor, '--warn': theme.warningColor, '--danger': theme.errorColor,
  }">
    <div v-if="(ui.error || ['error', 'conflict'].includes(ui.saveState)) && !ui.settingsOpen && !ui.nodeDraft" class="feedback" role="alert">
      <span>{{ ui.error || t(ui.saveState === 'conflict' ? 'pipeline.conflict' : 'pipeline.saveFailed') }}</span>
      <NPopconfirm v-if="ui.saveState === 'conflict'" @positive-click="ui.load()">
        <template #trigger><NButton size="tiny">{{ t('pipeline.reload') }}</NButton></template>
        {{ t('pipeline.discard') }}
      </NPopconfirm>
      <NButton v-else-if="ui.saveState === 'error'" size="tiny" @click="ui.retrySave()">{{ t('pipeline.retrySave') }}</NButton>
      <NButton v-else-if="!ui.config" size="tiny" @click="ui.load()">{{ t('common.refresh') }}</NButton>
    </div>
    <NSpin v-if="!ui.config && !ui.error" size="small" :description="t('pipeline.loading')" />
    <template v-if="ui.config && ui.profile">
      <div class="editor-frame">
        <div class="toolbar" role="group" :aria-label="t('pipeline.title')">
          <div class="actions">
            <NButton size="small" type="primary" :disabled="!ui.canRun" @click="ui.execute('run')">
              <template #icon><Play :size="15" aria-hidden="true" /></template>{{ t('pipeline.run') }}
            </NButton>
            <NButton v-if="ui.active" size="small" :disabled="ui.cancelPending" @click="ui.cancel()">
              <template #icon><X :size="15" aria-hidden="true" /></template>{{ t('pipeline.cancelRun') }}
            </NButton>
            <NButton v-else size="small" :disabled="!ui.canRun" @click="ui.execute('stop')">
              <template #icon><Square :size="13" aria-hidden="true" /></template>{{ t('pipeline.stop') }}
            </NButton>
          </div>
          <div class="actions layout-actions">
            <NButton size="small" quaternary :disabled="ui.locked" @click="ui.addGroup()">
              <template #icon><Plus :size="16" aria-hidden="true" /></template>{{ t('pipeline.addGroup') }}
            </NButton>
            <NButton size="small" quaternary :disabled="ui.locked || !ui.nodes.length" @click="ui.autoLayout()">
              <template #icon><LayoutGrid :size="15" aria-hidden="true" /></template>{{ t('pipeline.arrange') }}
            </NButton>
          </div>
          <NButton class="settings-button" size="small" quaternary :title="t('pipeline.settings')"
            :aria-label="t('pipeline.settings')" aria-haspopup="dialog" @click="ui.settingsOpen = true">
            <Settings :size="17" aria-hidden="true" />
          </NButton>
        </div>

        <div class="pipeline-canvas" :aria-label="t('pipeline.canvas')" role="region"
          @dragover.prevent @drop.prevent="ui.onDrop">
          <VueFlow :nodes="ui.nodes" :edges="ui.edges" :apply-default="false" fit-view-on-init :max-zoom="1.5"
            :nodes-draggable="!ui.locked" :nodes-connectable="!ui.locked" :nodes-focusable="false"
            :zoom-on-double-click="false" :elevate-nodes-on-select="false" :node-drag-threshold="4"
            :delete-key-code="['Backspace', 'Delete']" :selection-key-code="null" :multi-selection-key-code="null"
            @init="ui.onInit" @nodes-change="ui.onNodesChange" @edges-change="ui.onEdgesChange"
            @node-drag-start="ui.onDragStart" @node-drag-stop="ui.onDragStop" @connect="ui.onConnect"
            @connect-start="ui.onGestureStart" @connect-end="ui.onGestureEnd">
            <template #node-pipelineGroup="{ data }"><PipelineGroupNode :data="data" /></template>
            <template #node-pipelineApp="{ data }"><PipelineAppNode :data="data" /></template>
          </VueFlow>
          <p v-if="!ui.nodes.length" class="empty-canvas">{{ t('pipeline.emptyCanvas') }}</p>
        </div>

        <div class="tray">
          <button type="button" class="tray-toggle" :aria-expanded="ui.trayOpen" aria-controls="pipeline-pool"
            @click="ui.trayOpen = !ui.trayOpen">
            <ChevronRight :size="15" aria-hidden="true" />
            {{ t('pipeline.unassigned') }} <span class="count">{{ ui.pool.length }}</span>
          </button>
          <div v-show="ui.trayOpen" id="pipeline-pool" class="tray-body">
            <p class="tray-hint">{{ t(ui.pool.length ? 'pipeline.poolHint' : 'pipeline.noUnassigned') }}</p>
            <div v-if="ui.pool.length" class="pool-apps">
              <button v-for="app in ui.pool" :key="app.app_id" type="button" class="pool-app" :data-app-id="app.app_id"
                :disabled="ui.locked" :draggable="!ui.locked" :aria-label="t('pipeline.assign', { app: ui.appName(app.app_id) })"
                :title="t('pipeline.assign', { app: ui.appName(app.app_id) })" @dragstart="ui.onTrayDrag($event, app.app_id)"
                @dragend="ui.onGestureEnd" @click="ui.addFromPool(app.app_id)">
                <img :src="ui.appIcon(app.app_id)" alt="" draggable="false" @error.once="$event.target.src = '/app-default-icon.png'">
                <span>{{ ui.appName(app.app_id) }}</span><Plus :size="13" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="editor-status" role="status" aria-live="polite">
        <span v-if="ui.profileProgress">{{ ui.statusName(ui.profileProgress.status) }}</span>
        <span v-if="ui.connectionLost">{{ t('pipeline.reconnecting') }}</span>
        <span v-if="['pending', 'saving', 'saved'].includes(ui.saveState)">{{ t(`pipeline.saveStates.${ui.saveState}`) }}</span>
      </div>
      <PipelineSettingsDrawer />
      <PipelineNodeConfigDrawer />
    </template>
  </section>
</template>

<style scoped>
.pipeline { display: grid; min-width: 0; gap: 8px; color: var(--ink); }
.editor-frame { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); min-width: 0; overflow: hidden; }
.toolbar, .actions, .feedback, .editor-status { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.toolbar { padding: 10px 12px; border-bottom: 1px solid var(--line); }
.layout-actions { border-inline-start: 1px solid var(--line); padding-inline-start: 7px; }
.settings-button { margin-inline-start: auto; }
.pipeline-canvas { position: relative; height: clamp(340px, 57vh, 660px); background-color: var(--paper);
  background-image: radial-gradient(circle, color-mix(in srgb, var(--muted) 22%, transparent) 1px, transparent 1px); background-size: 16px 16px; }
.pipeline-canvas :deep(.vue-flow) { --vf-connection-path: var(--accent); }
.pipeline-canvas :deep(.vue-flow__edge-path) { stroke: var(--muted); stroke-width: 1.6; }
.pipeline-canvas :deep(.pipeline-derived-edge), .pipeline-canvas :deep(.pipeline-derived-edge path) { pointer-events: none; }
@media (prefers-reduced-motion: reduce) { .pipeline-canvas :deep(.vue-flow__edge.animated path) { animation: none; } }
.pipeline-canvas :deep(.vue-flow__edge:is(.selected, :focus-visible) .vue-flow__edge-path) { stroke: var(--accent); stroke-width: 2.5; }
.empty-canvas { position: absolute; top: 48%; inset-inline: 16px; margin: 0 auto; max-width: 36ch; text-align: center; color: var(--muted); pointer-events: none; }
.tray { border-top: 1px solid var(--line); }
.tray-toggle, .pool-app { display: inline-flex; align-items: center; gap: 8px; font: inherit; color: inherit; cursor: pointer; }
.tray-toggle { width: 100%; border: 0; background: transparent; text-align: start; padding: 10px 14px; font-weight: 600; }
.tray-toggle[aria-expanded="true"] svg { transform: rotate(90deg); }
.count { font-size: 12px; font-variant-numeric: tabular-nums; color: var(--muted); }
.tray-body { padding: 0 14px 12px; }
.tray-hint { margin: 0; font-size: 12px; color: var(--muted); }
.pool-apps { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; max-height: 118px; overflow-y: auto; padding: 2px; }
.pool-app { gap: 7px; min-height: 31px; max-width: 100%; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); padding: 3px 8px 3px 4px; }
.pool-app img { flex: none; width: 22px; height: 22px; object-fit: contain; border-radius: 4px; }
.pool-app span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pool-app svg { flex: none; color: var(--muted); }
.pool-app:hover:not(:disabled) { border-color: var(--accent); }
.pool-app:disabled { cursor: default; opacity: .6; }
.tray-toggle:focus-visible, .pool-app:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.feedback, .editor-status { font-size: 13px; color: var(--muted); }
.feedback { border-inline-start: 3px solid var(--danger); padding-inline-start: 8px; overflow-wrap: anywhere; }
.editor-status:empty { display: none; }
.editor-status { justify-content: flex-end; }
@media (max-width: 640px) {
  .toolbar { gap: 4px; padding: 8px; }
  .layout-actions { padding-inline-start: 0; border: none; }
  .actions { gap: 2px; }
  .pipeline-canvas { height: clamp(310px, 50vh, 460px); }
}
</style>

<!-- Shared by both teleported Naive UI drawers, not global application controls. -->
<style>
.pipeline-form { display: grid; align-content: start; gap: 15px; font-size: 14px; }
.pipeline-form fieldset { display: grid; gap: 10px; min-width: 0; margin: 0; border: 0; padding: 0; }
.pipeline-form fieldset + fieldset { border-top: var(--n-header-border-bottom); padding-top: 16px; }
.pipeline-form legend { padding: 0 0 6px; font-weight: 650; }
.pipeline-form .field { display: grid; gap: 4px; min-width: 0; }
.pipeline-form :is(input:not([type="checkbox"]), select, textarea) { box-sizing: border-box; width: 100%; min-width: 0;
  padding: 6px 9px; font: inherit; line-height: 1.45; color: inherit; background-color: var(--n-color);
  border: 1px solid color-mix(in srgb, currentColor 36%, transparent); border-radius: 6px; }
.pipeline-form :is(input, select, textarea):focus-visible { outline: 2px solid var(--pipeline-focus); outline-offset: 1px; }
.pipeline-form input[type="checkbox"] { margin: 0; width: 16px; height: 16px; accent-color: var(--pipeline-focus); flex: none; }
.pipeline-form .check { display: flex; gap: 8px; align-items: center; overflow-wrap: anywhere; }
.pipeline-form .form-pair { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 8px; }
.pipeline-form .form-pair > .field { flex: 1 1 100px; }
.pipeline-form .form-hint { margin: 0; font-size: 12px; }
</style>
