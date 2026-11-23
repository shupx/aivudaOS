<script setup>
import { toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueDraggable } from 'vue-draggable-plus'
import { NAlert, NButton, NDropdown, NInput, NModal, NPopconfirm, NSelect, NSpin, NSwitch, NTag, NText, useThemeVars } from 'naive-ui'
import { Ellipsis, GripVertical, Play, Plus, Settings2, Square } from 'lucide-vue-next'
import PipelineNodeConfigDrawer from './PipelineNodeConfigDrawer.vue'
import { useStartupPipeline } from '../../composables/useStartupPipeline'

const props = defineProps({ apps: { type: Array, required: true } })
const { t } = useI18n(), theme = useThemeVars()
const {
  config, profile, selected, dirty, locked, busy, error, notice, pool, analysis, preview,
  checked, conflicts, appMap, appName, groupName, statusName, probeSummary, modes, policies,
  probeOptions, profileOptions, groupOptions, dependencyOptions, destination, position, maxPosition,
  nodeDraft, changeProbe, editNode, submitNode, nameDialog, nameValid, openName, submitName, addFromPool,
  stageActions, stageAction, reorderGroups, reorderNodes, template, save, validate, load, execute, cancel,
  active, canRun, progress, profileProgress, connectionLost, cancelPending,
} = useStartupPipeline(toRef(props, 'apps'))
</script>

<template>
  <section class="pipeline" :aria-label="t('pipeline.title')" :style="{
    '--surface': theme.cardColor, '--line': theme.dividerColor, '--tint': theme.actionColor,
    '--muted': theme.textColor3, '--accent': theme.primaryColor, '--danger': theme.errorColor,
  }">
    <NAlert v-if="error" type="error" role="alert">{{ error }} <NButton v-if="!config" size="small" @click="load">{{ t('common.refresh') }}</NButton></NAlert>
    <NSpin v-if="!config && !error" size="small" :description="t('pipeline.loading')" />
    <template v-if="config && profile">
      <header class="toolbar">
        <div class="control-row">
          <label>{{ t('pipeline.profile') }} <NSelect v-model:value="selected" :options="profileOptions" :disabled="locked" size="small" /></label>
          <NButton size="small" secondary :disabled="locked" :aria-label="t('pipeline.addProfile')" :title="t('pipeline.addProfile')" @click="openName('addProfile')"><Plus :size="16"/></NButton>
          <NTag v-if="selected === config.default_profile" size="small" :bordered="false">{{ t('pipeline.defaultProfile') }}</NTag>
          <NButton v-else text size="small" :disabled="locked" @click="config.default_profile = selected">{{ t('pipeline.makeDefault') }}</NButton>
          <label>{{ t('pipeline.onFailure') }} <NSelect v-model:value="profile.on_failure" :options="policies" :disabled="locked" size="small" /></label>
        </div>
        <div class="control-row">
          <label :title="t('pipeline.takeoverHint')"><NSwitch v-model:value="config.takeover_autostart" size="small" :disabled="locked" :aria-label="t('pipeline.takeover')" /> {{ t('pipeline.takeover') }}</label>
          <NButton size="small" :disabled="locked" @click="template">{{ t('pipeline.template') }}</NButton>
          <NButton size="small" :loading="busy === 'validate'" :disabled="locked" @click="validate">{{ t('pipeline.validate') }}</NButton>
          <NPopconfirm v-if="dirty" :disabled="locked" @positive-click="load">
            <template #trigger><NButton size="small" :disabled="locked">{{ t('pipeline.reload') }}</NButton></template>{{ t('pipeline.discard') }}
          </NPopconfirm>
          <NButton v-else size="small" :disabled="locked" @click="load">{{ t('pipeline.reload') }}</NButton>
          <NButton size="small" type="primary" :loading="busy === 'save'" :disabled="locked || !dirty" @click="save">{{ t('pipeline.save') }}</NButton>
        </div>
        <div class="run-row control-row">
          <NButton size="small" secondary type="primary" :disabled="!canRun" @click="execute('run')"><template #icon><Play :size="15" /></template>{{ t('pipeline.run') }}</NButton>
          <NButton size="small" secondary :disabled="!canRun" @click="execute('stop')"><template #icon><Square :size="14" /></template>{{ t('pipeline.stop') }}</NButton>
          <NButton v-if="active" size="small" type="warning" :loading="cancelPending" :disabled="!!busy || cancelPending" @click="cancel">{{ t('pipeline.cancelRun') }}</NButton>
          <NText v-if="dirty || notice" depth="3" role="status">{{ t(`pipeline.${dirty ? 'unsaved' : notice}`) }}</NText>
        </div>
      </header>
      <NAlert v-if="analysis.errors.length || checked?.errors?.length" type="error" :title="t('pipeline.conflicts')">
        <ul class="issues"><li v-for="(issue, i) in analysis.errors" :key="i">{{ t(`pipeline.issues.${issue.code}`, { apps: issue.apps.join(', '), dep: issue.dependency }) }}</li>
          <li v-for="(message, i) in checked?.errors" :key="'server-' + i">{{ message }}</li></ul>
      </NAlert>
      <section v-if="progress" class="operation surface" :aria-label="t('pipeline.operation')">
        <div class="control-row"><h3>{{ t('pipeline.operation') }}</h3>
          <NTag size="small" :type="progress.status === 'failed' ? 'error' : 'info'" role="status">{{ statusName(progress.status) }}</NTag>
          <NText depth="3">{{ progress.profile }}<template v-if="progress.group_id"> / {{ groupName(profile.groups.find(g => g.id === progress.group_id)) || progress.group_id }}</template></NText>
        </div>
        <p v-if="connectionLost" role="status">{{ t('pipeline.reconnecting') }}</p>
        <details v-if="progress.logs.length"><summary>{{ t('pipeline.log') }} ({{ progress.logs.length }})</summary><pre>{{ progress.logs.join('\n') }}</pre></details>
      </section>
      <div class="workspace">
        <div class="stages">
          <div class="section-heading"><h3>{{ t('pipeline.stageOrder') }}</h3>
            <NButton size="small" secondary :disabled="locked" @click="openName('addStage')"><template #icon><Plus :size="15" /></template>{{ t('pipeline.addStage') }}</NButton></div>
          <p class="help">{{ t('pipeline.orderHint') }}</p>
          <VueDraggable :model-value="profile.groups" handle=".stage-grip" draggable=".stage" :disabled="locked" @update:model-value="reorderGroups" class="stage-list">
            <article v-for="(group, index) in profile.groups" :key="group.id" class="stage surface" :data-enabled="group.enabled">
              <header class="stage-header">
                <span class="grip stage-grip" :title="t('pipeline.dragStage')"><GripVertical :size="16" /></span>
                <span class="ordinal" :aria-label="t('pipeline.stageNumber', { n: index + 1 })">{{ index + 1 }}</span>
                <h4>{{ groupName(group) }}</h4>
                <NTag v-if="profileProgress?.stages.has(group.id)" size="small" :bordered="false">{{ statusName(profileProgress.stages.get(group.id)) }}</NTag>
                <div class="stage-controls">
                  <NSelect v-model:value="group.mode" :options="modes" :disabled="locked" size="small" :aria-label="t('pipeline.mode')" />
                  <NSwitch v-model:value="group.enabled" size="small" :disabled="locked" :aria-label="t('pipeline.includeStage')" :title="t('pipeline.includeStage')" />
                  <NDropdown trigger="click" :options="stageActions(group, index)" @select="stageAction($event, group, index)">
                    <NButton size="small" quaternary :disabled="locked" :aria-label="t('pipeline.stageActions', { name: groupName(group) })"><Ellipsis :size="18" /></NButton>
                  </NDropdown>
                </div>
              </header>
              <VueDraggable :model-value="group.items" group="pipeline-apps" handle=".node-grip" draggable=".node" :disabled="locked" class="drop-list" :data-empty="t('pipeline.dropHere')" @update:model-value="reorderNodes(group, $event)">
                <div v-for="node in group.items" :key="node.app_id" class="node" :class="{ conflict: conflicts.has(node.app_id), editable: !locked }" @click="!locked && editNode(node, group)">
                  <span class="grip node-grip" :title="t('pipeline.dragNode')"><GripVertical :size="16" /></span>
                  <div class="node-info">
                    <div class="node-title"><strong>{{ appName(node.app_id) }}</strong>
                      <NText depth="3" v-if="appName(node.app_id) !== node.app_id">{{ node.app_id }}</NText>
                    </div>
                    <div class="badges"><NTag size="tiny" :bordered="false" :type="appMap.get(node.app_id)?.running ? 'success' : 'default'">{{ t(appMap.get(node.app_id)?.running ? 'pipeline.runtimeRunning' : 'pipeline.runtimeStopped') }}</NTag>
                      <NTag size="tiny" :type="profileProgress?.nodes.get(node.app_id) === 'waiting_ready' ? 'warning' : 'default'">
                        <template v-if="profileProgress?.nodes.get(node.app_id) === 'waiting_ready' && active" #icon><NSpin :size="11" /></template>
                        {{ statusName(profileProgress?.nodes.get(node.app_id) || (group.enabled && node.enabled ? 'idle' : 'disabled')) }}
                      </NTag>
                    </div>
                    <div class="node-summary">{{ t('pipeline.readiness') }}: {{ probeSummary(node.readiness) }}</div>
                    <div class="node-summary badges">{{ t('pipeline.dependsOn') }}:
                      <NTag v-for="dep in node.depends_on" :key="dep" size="tiny" :bordered="false">{{ dep }}</NTag>
                      <span v-if="!node.depends_on?.length">{{ t('pipeline.noDeps') }}</span>
                    </div>
                  </div>
                  <NButton size="small" quaternary :disabled="locked" :aria-label="t('pipeline.editApp', { app: appName(node.app_id) })" :title="t('pipeline.configureNode')" @click.stop="editNode(node, group)"><Settings2 :size="16" /></NButton>
                </div>
              </VueDraggable>
            </article>
          </VueDraggable>
          <p v-if="!profile.groups.length" class="empty surface">{{ t('pipeline.noStages') }}</p>
        </div>
        <aside class="pool surface">
          <h3>{{ t('pipeline.unassigned') }} <NText depth="3">({{ pool.length }})</NText></h3>
          <p class="help">{{ t('pipeline.poolHint') }}</p>
          <VueDraggable :model-value="pool" group="pipeline-apps" handle=".pool-grip" draggable=".pool-node" :sort="false" :disabled="locked" class="drop-list" :data-empty="t('pipeline.noUnassigned')">
            <div v-for="node in pool" :key="node.app_id" class="pool-node">
              <span class="grip pool-grip" :title="t('pipeline.dragNode')"><GripVertical :size="16" /></span>
              <div class="node-info"><strong>{{ appName(node.app_id) }}</strong><div v-if="appName(node.app_id) !== node.app_id" class="node-summary">{{ node.app_id }}</div></div>
              <NDropdown trigger="click" :options="groupOptions" key-field="value" @select="addFromPool(node.app_id, $event)">
                <NButton size="small" quaternary :disabled="locked || !groupOptions.length" :aria-label="t('pipeline.assign', { app: appName(node.app_id) })" :title="t('pipeline.assign', { app: appName(node.app_id) })"><Plus :size="15" /></NButton>
              </NDropdown>
            </div>
          </VueDraggable>
        </aside>
      </div>
      <section class="surface preview">
        <h3>{{ t('pipeline.preview') }}</h3>
        <p v-if="!preview.length" class="help">{{ t('pipeline.noPreview') }}</p>
        <ol v-else><li v-for="stage in preview" :key="stage.group_id"><strong>{{ groupName(profile.groups.find(g => g.id === stage.group_id)) || stage.group_id }}</strong>
          <span v-for="(batch, i) in stage.batches" :key="i" class="batch">{{ t('pipeline.batch', { n: i + 1 }) }}: {{ batch.join(', ') }}</span>
          <NText v-if="!stage.batches.length" depth="3">{{ t('pipeline.emptyStage') }}</NText>
        </li></ol>
      </section>
    </template>
    <PipelineNodeConfigDrawer :node="nodeDraft" :name="appName(nodeDraft?.app_id)" v-model:destination="destination" v-model:position="position" :max-position="maxPosition" :groups="groupOptions" :dependencies="dependencyOptions" :probes="probeOptions" @close="nodeDraft = null" @apply="submitNode" @change-probe="changeProbe" />
    <NModal :show="!!nameDialog" preset="dialog" :show-icon="false" :title="nameDialog && t(`pipeline.${nameDialog.kind}`)" @update:show="nameDialog = null">
      <template v-if="nameDialog?.kind === 'removeStage'">{{ t('pipeline.confirmRemove', { name: nameDialog.value }) }}</template>
      <NInput v-else-if="nameDialog" v-model:value="nameDialog.value" :placeholder="t('pipeline.name')" :aria-label="t('pipeline.name')" @keydown.enter.prevent="submitName" />
      <template #action><NButton size="small" @click="nameDialog = null">{{ t('common.cancel') }}</NButton>
        <NButton size="small" :type="nameDialog?.kind === 'removeStage' ? 'error' : 'primary'" :disabled="!nameValid" @click="submitName">{{ t(nameDialog?.kind === 'removeStage' ? 'pipeline.removeStage' : 'pipeline.apply') }}</NButton></template>
    </NModal>
  </section>
</template>

<style scoped>
.pipeline { display: grid; gap: 18px; font-size: 14px; min-width: 0; }
.pipeline h3, .pipeline h4 { margin: 0; font-size: 16px; font-weight: 600; line-height: 1.4; }
.pipeline h4 { font-size: 15px; overflow-wrap: anywhere; }
.toolbar { display: grid; gap: 12px; }
.control-row, .section-heading, .stage-header, .stage-controls, .node, .pool-node, .badges, .node-title { display: flex; align-items: center; gap: 8px; }
.control-row, .stage-header, .badges, .node-title { flex-wrap: wrap; }
.control-row label { display: flex; align-items: center; gap: 8px; max-width: 100%; }
.control-row .n-select { width: auto; min-width: 104px; max-width: 190px; }
.run-row { padding-top: 12px; border-top: 1px solid var(--line); }
.workspace { display: grid; gap: 20px; grid-template-columns: minmax(0, 1fr) minmax(180px, 26%); align-items: start; }
.surface { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.section-heading { justify-content: space-between; }
.help, .node-summary, .node-title .n-text, .empty { color: var(--muted); font-size: 13px; }
.help { margin: 6px 0 12px; max-width: 75ch; }
.stage-list { display: grid; gap: 12px; }
.stage { min-width: 0; overflow: hidden; }
.stage-header { padding: 10px; background: var(--tint); border-bottom: 1px solid var(--line); }
.stage-controls { margin-inline-start: auto; gap: 6px; }
.stage-controls .n-select { width: 112px; }
.ordinal { font-variant-numeric: tabular-nums; font-weight: 650; color: var(--accent); padding-inline-end: 6px; border-inline-end: 1px solid var(--line); }
.stage[data-enabled="false"] .ordinal { color: var(--muted); }
.grip { display: inline-flex; cursor: grab; color: var(--muted); touch-action: none; padding: 6px 0; flex: none; }
.grip:active { cursor: grabbing; }
.drop-list { min-height: 48px; padding: 4px 10px; }
.drop-list:empty::before { content: attr(data-empty); display: block; font-size: 13px; padding: 10px 0; color: var(--muted); pointer-events: none; }
.node, .pool-node { padding: 8px 0; align-items: flex-start; }
.node + .node, .pool-node + .pool-node { border-top: 1px solid var(--line); }
.node.editable { cursor: pointer; }
.node.conflict { box-shadow: inset 3px 0 var(--danger); padding-inline-start: 8px; }
.node-info { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.badges { margin: 3px 0; }
.pool, .preview, .operation, .empty { padding: 14px; }
.pool .drop-list { padding: 0; }
.pool .help { margin-bottom: 6px; }
.issues, .preview ol { margin: 8px 0 0; padding-inline-start: 24px; }
.preview li { padding: 3px 0; overflow-wrap: anywhere; }
.batch, .preview li > .n-text { margin-inline-start: 12px; font-size: 13px; }
.operation details { margin-top: 8px; }
.operation summary { cursor: pointer; }
.operation pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 200px; overflow: auto; }
@media (max-width: 950px) { .workspace { grid-template-columns: minmax(0, 1fr); } .pool { grid-row: 1; } }
@media (max-width: 600px) { .stage-controls { flex-wrap: wrap; } .control-row label { flex-wrap: wrap; } .control-row { gap: 6px; } }
</style>
