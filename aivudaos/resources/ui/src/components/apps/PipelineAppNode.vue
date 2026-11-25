<script setup>
import { computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({ data: { type: Object, required: true } })
const ui = inject('pipelineEditor'), { t } = useI18n()
const id = computed(() => props.data.appId)
const name = computed(() => ui.appName(id.value))
const item = computed(() => ui.itemsById.get(id.value))
const status = computed(() => ui.nodeStatus(id.value, props.data.groupId))
const badge = computed(() => ui.readinessBadge(item.value?.readiness))
</script>

<template>
  <div class="pipeline-app" :data-app-id="data.appId" :data-group-id="data.groupId">
    <Handle type="target" :position="Position.Left" :connectable="!ui.locked" />
    <button type="button" class="app-face" :title="t('pipeline.editApp', { app: name })" :disabled="ui.locked"
      :aria-label="t('pipeline.editApp', { app: name })" :aria-describedby="`app-state-${id}`"
      @click.stop="ui.editNode(id)" @keydown.enter.stop @keydown.space.stop>
      <img :src="ui.appIcon(id)" alt="" draggable="false" @error.once="$event.target.src = '/app-default-icon.png'">
      <span class="app-labels"><strong>{{ name }}</strong><small v-if="badge">{{ badge }}</small></span>
      <span :id="`app-state-${id}`" class="status-dot" role="img" :data-status="status"
        :title="ui.statusName(status)" :aria-label="ui.statusName(status)" />
    </button>
    <Handle type="source" :position="Position.Right" :connectable="!ui.locked" />
  </div>
</template>

<style scoped>
.pipeline-app { box-sizing: border-box; width: 100%; height: 100%; }
.app-face { box-sizing: border-box; width: 100%; height: 100%; display: flex; gap: 7px; align-items: center; padding: 6px 12px;
  border: 1px solid color-mix(in srgb, var(--muted) 50%, var(--surface)); border-radius: 7px;
  font: inherit; color: var(--ink); background: var(--surface); text-align: start; cursor: inherit; }
.app-face:hover:not(:disabled), .app-face:focus-visible { border-color: var(--accent); }
.app-face:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.app-face img { flex: none; width: 27px; height: 27px; object-fit: contain; border-radius: 5px; }
.app-labels { display: grid; gap: 1px; min-width: 0; flex: 1; }
.app-labels strong, .app-labels small { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.app-labels strong { font-weight: 600; font-size: 13px; line-height: 1.35; }
.app-labels small { color: var(--muted); font-size: 11px; line-height: 1.25; }
.status-dot { flex: none; box-sizing: border-box; width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--muted); }
.status-dot:is([data-status="running"], [data-status="active"], [data-status="completed"]) { border-color: var(--ok); background: var(--ok); }
.status-dot:is([data-status="starting"], [data-status="stopping"], [data-status="cancelling"]) { border: 2px solid var(--accent); border-inline-end-color: transparent; }
.status-dot[data-status="waiting_ready"] { width: 9px; height: 9px; transform: rotate(45deg); border: 2px solid var(--accent); border-radius: 1px; }
.status-dot[data-status="queued"] { border: 1.5px dashed var(--accent); }
.status-dot[data-status="degraded"] { border: none; background: var(--warn); border-radius: 1px; clip-path: polygon(50% 0, 100% 100%, 0 100%); }
.status-dot[data-status="failed"] { border-radius: 1px; border: none; background: var(--danger); clip-path: polygon(20% 0, 50% 30%, 80% 0, 100% 20%, 70% 50%, 100% 80%, 80% 100%, 50% 70%, 20% 100%, 0 80%, 30% 50%, 0 20%); }
.status-dot:is([data-status="skipped"], [data-status="disabled"], [data-status="stopped"], [data-status="canceled"]) { border-radius: 1px; }
.pipeline-app :deep(.vue-flow__handle) { width: 9px; height: 9px; background: var(--surface); border: 2px solid var(--muted); }
.pipeline-app :deep(.vue-flow__handle:hover), .pipeline-app :deep(.vue-flow__handle.connecting) { border-color: var(--accent); }
</style>
