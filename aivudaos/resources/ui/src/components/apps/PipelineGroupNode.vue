<script setup>
import { computed, inject, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'
import { NPopconfirm } from 'naive-ui'
import { Columns2, ListOrdered, Play, Trash2 } from 'lucide-vue-next'

const props = defineProps({ data: { type: Object, required: true } })
const ui = inject('pipelineEditor'), { t } = useI18n()
const group = computed(() => ui.groupsById.get(props.data.groupId))
const name = computed(() => ui.groupName(group.value))
const state = computed(() => ui.stageStates.get(props.data.groupId))
const edit = ref(false), text = ref(''), input = ref(null), nameButton = ref(null)
const modeLabel = computed(() => group.value && t('pipeline.groupMode', { name: name.value, mode: t(`pipeline.modes.${group.value.mode}`) }))

async function beginRename() {
  if (ui.locked) return
  text.value = name.value
  edit.value = true
  await nextTick()
  input.value?.select()
}
function finishRename(apply, restoreFocus = false) {
  if (!edit.value) return
  edit.value = false
  if (apply && text.value.trim() && text.value.trim() !== name.value) ui.renameGroup(props.data.groupId, text.value.trim())
  if (restoreFocus) nextTick(() => nameButton.value?.focus())
}
</script>

<template>
  <div v-if="group" class="pipeline-group" :data-group-id="data.groupId" :data-disabled="group.enabled === false">
    <Handle class="stage-anchor" type="target" :position="Position.Left" :connectable="false" />
    <Handle class="stage-anchor" type="source" :position="Position.Right" :connectable="false" />
    <header class="group-header">
      <span class="order" :title="t('pipeline.groupOrder', { n: group.order + 1 })">{{ group.order + 1 }}</span>
      <input v-if="edit" ref="input" v-model="text" class="name-input nodrag nopan" type="text"
        :aria-label="t('pipeline.groupName')" @blur="finishRename(true)" @keydown.stop
        @keydown.enter.prevent="finishRename(true, true)" @keydown.esc.prevent="finishRename(false, true)">
      <button v-else ref="nameButton" type="button" class="group-name" :disabled="ui.locked"
        :title="t('pipeline.groupKeys', { name })" :aria-label="t('pipeline.renameGroup', { name })"
        aria-keyshortcuts="Enter Alt+ArrowUp Alt+ArrowDown" @dblclick.stop="beginRename"
        @keydown.enter.stop.prevent="beginRename" @keydown.space.stop.prevent="beginRename"
        @keydown.alt.up.stop.prevent="ui.moveGroup(data.groupId, -1)" @keydown.alt.down.stop.prevent="ui.moveGroup(data.groupId, 1)">{{ name }}</button>
      <div class="group-actions nodrag nopan">
        <button type="button" :aria-label="modeLabel" :title="modeLabel" :disabled="ui.locked" @click.stop="ui.toggleMode(data.groupId)">
          <component :is="group.mode === 'parallel' ? Columns2 : ListOrdered" :size="15" aria-hidden="true" />
        </button>
        <button type="button" :aria-label="t('pipeline.runGroup', { name })" :title="t('pipeline.runGroup', { name })"
          :disabled="!ui.canRun || !group.enabled" @click.stop="ui.execute('run', data.groupId)"><Play :size="14" aria-hidden="true" /></button>
        <NPopconfirm :disabled="ui.locked" @positive-click="ui.removeGroup(data.groupId)">
          <template #trigger>
            <button type="button" :aria-label="t('pipeline.deleteGroup', { name })" :title="t('pipeline.deleteGroup', { name })"
              :disabled="ui.locked" @click.stop><Trash2 :size="14" aria-hidden="true" /></button>
          </template>{{ t('pipeline.confirmRemove', { name }) }}
        </NPopconfirm>
      </div>
    </header>
    <span v-if="state" class="stage-state" role="status">{{ ui.statusName(state) }}</span>
    <span v-if="!group.items.length" class="group-empty">{{ t('pipeline.dropHere') }}</span>
  </div>
</template>

<style scoped>
.pipeline-group { position: relative; box-sizing: border-box; width: 100%; height: 100%; border: 1.5px dashed color-mix(in srgb, var(--muted) 65%, transparent); border-radius: 9px; color: var(--ink); }
.pipeline-group :deep(.stage-anchor) { opacity: 0; pointer-events: none; }
.group-header { display: flex; align-items: center; gap: 6px; padding: 6px 8px; box-sizing: border-box; height: 39px; background: color-mix(in srgb, var(--surface) 85%, transparent); border-radius: 8px 8px 0 0; }
.order { font-variant-numeric: tabular-nums; font-size: 12px; font-weight: 650; color: var(--muted); padding-inline-end: 6px; border-inline-end: 1px solid var(--line); }
.group-header :is(button, input) { color: inherit; font-family: inherit; border: 0; background: transparent; }
.group-name, .name-input { flex: 1; min-width: 0; padding: 1px 2px; font-size: 14px; font-weight: 650; }
.group-name { text-align: start; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: inherit; }
.name-input { background: var(--surface); }
.group-actions { display: flex; gap: 1px; align-items: center; }
.group-actions button { display: grid; place-items: center; width: 25px; height: 25px; padding: 0; cursor: pointer; border-radius: 4px; }
.group-actions button:hover:not(:disabled) { color: var(--accent); background: var(--paper); }
.group-actions button:disabled { opacity: .45; cursor: default; }
.group-header :is(button, input):focus-visible { outline: 2px solid var(--accent); }
.group-empty { position: absolute; inset: 39px 6px 0; display: grid; place-items: center; color: var(--muted); font-size: 12px; pointer-events: none; }
.stage-state { position: absolute; right: 8px; bottom: -7px; background: var(--paper); font-size: 11px; line-height: 14px; padding: 0 4px; border-radius: 3px; color: var(--muted); }
.pipeline-group[data-disabled="true"] { border-style: dotted; }
</style>
