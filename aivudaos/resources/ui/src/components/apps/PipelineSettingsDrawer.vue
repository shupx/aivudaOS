<script setup>
import { inject, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, useThemeVars } from 'naive-ui'
import { ArrowDown, ArrowUp } from 'lucide-vue-next'

const ui = inject('pipelineEditor'), { t } = useI18n(), theme = useThemeVars()
const profileName = ref('')
</script>

<template>
  <NDrawer v-model:show="ui.settingsOpen" placement="right" width="min(370px, 100vw)" :aria-label="t('pipeline.settings')">
    <NDrawerContent :title="t('pipeline.settings')" closable :body-content-style="{ padding: '16px 20px' }">
      <div class="pipeline-form" :style="{ '--pipeline-focus': theme.primaryColor }">
        <div v-if="ui.error" class="settings-error" role="alert"><span>{{ ui.error }}</span>
          <small v-if="ui.saveState === 'conflict'">{{ t('pipeline.conflictHelp') }}</small>
        </div>
        <fieldset :disabled="ui.locked">
          <div class="form-pair">
            <label class="field">{{ t('pipeline.profile') }}
              <select :value="ui.selected" @change="ui.selectProfile($event.target.value)">
                <option v-for="p in ui.profileOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
              </select>
            </label>
            <NButton size="small" :disabled="ui.locked || ui.selected === ui.config.default_profile" @click="ui.makeDefault()">
              {{ t(ui.selected === ui.config.default_profile ? 'pipeline.defaultProfile' : 'pipeline.makeDefault') }}
            </NButton>
          </div>
          <form class="form-pair" @submit.prevent="ui.addProfile(profileName.trim()); profileName = ''">
            <label class="field">{{ t('pipeline.profileName') }}
              <input type="text" v-model="profileName" required autocomplete="off">
            </label>
            <NButton size="small" attr-type="submit" :disabled="ui.locked || !profileName.trim() || ui.profileOptions.some(p => p.value === profileName.trim())">{{ t('pipeline.addProfile') }}</NButton>
          </form>
        </fieldset>
        <fieldset :disabled="ui.locked">
          <label class="field">{{ t('pipeline.onFailure') }}
            <select :value="ui.profile.on_failure" @change="ui.setPolicy($event.target.value)">
              <option v-for="p in ui.policies" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </label>
          <label class="check"><input type="checkbox" role="switch" :checked="ui.config.takeover_autostart"
            aria-describedby="pipeline-takeover-help" @change="ui.setTakeover($event.target.checked)">{{ t('pipeline.takeover') }}</label>
          <p id="pipeline-takeover-help" class="form-hint">{{ t('pipeline.takeoverHint') }}</p>
        </fieldset>
        <details v-if="ui.profile.groups.length" class="group-order">
          <summary>{{ t('pipeline.orderSettings') }}</summary>
          <ol>
            <li v-for="(group, i) in ui.profile.groups" :key="group.id">
              <label class="check"><input type="checkbox" :checked="group.enabled" :disabled="ui.locked"
                :aria-label="t('pipeline.enableGroup', { name: ui.groupName(group) })"
                @change="ui.setGroupEnabled(group.id, $event.target.checked); $event.target.checked = group.enabled">{{ ui.groupName(group) }}</label>
              <NButton quaternary size="tiny" :disabled="ui.locked || !i"
                :aria-label="t('pipeline.earlier', { name: ui.groupName(group) })" :title="t('pipeline.earlier', { name: ui.groupName(group) })"
                @click="ui.moveGroup(group.id, -1)"><ArrowUp :size="14" aria-hidden="true" /></NButton>
              <NButton quaternary size="tiny" :disabled="ui.locked || i + 1 === ui.profile.groups.length"
                :aria-label="t('pipeline.later', { name: ui.groupName(group) })" :title="t('pipeline.later', { name: ui.groupName(group) })"
                @click="ui.moveGroup(group.id, 1)"><ArrowDown :size="14" aria-hidden="true" /></NButton>
            </li>
          </ol>
        </details>
        <NButton size="small" class="template-button" :disabled="ui.locked" @click="ui.template()">{{ t('pipeline.template') }}</NButton>
      </div>
      <template #footer><NButton size="small" @click="ui.settingsOpen = false">{{ t('common.close') }}</NButton></template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.settings-error { display: grid; gap: 4px; color: v-bind('theme.errorColor'); overflow-wrap: anywhere; }
.group-order summary { cursor: pointer; }
.group-order ol { display: grid; gap: 4px; list-style: none; padding: 0; margin: 8px 0 0; }
.group-order li { display: flex; align-items: center; gap: 4px; }
.group-order .check { flex: 1; }
.template-button { justify-self: start; }
</style>
