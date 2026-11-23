<script setup>
import { computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, useThemeVars } from 'naive-ui'
import { readinessFields } from '../../services/core/startupPipeline.js'

const ui = inject('pipelineEditor'), { t } = useI18n(), theme = useThemeVars()
const node = computed(() => ui.nodeDraft)
</script>

<template>
  <NDrawer :show="!!node" placement="right" width="min(370px, 100vw)" :aria-label="t('pipeline.configureNode')"
    @update:show="!$event && ui.closeNode()">
    <NDrawerContent v-if="node" :title="t('pipeline.editApp', { app: ui.appName(node.app_id) })" closable
      :body-content-style="{ padding: '16px 20px' }">
      <form id="pipeline-node-form" class="pipeline-form" :style="{ '--pipeline-focus': theme.primaryColor }" @submit.prevent="ui.submitNode()">
        <fieldset :disabled="ui.locked || !ui.destination">
          <label class="field">{{ t('pipeline.probeType') }}
            <select :value="node.readiness.type" @change="ui.changeProbe($event.target.value)">
              <option v-for="option in ui.probeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <template v-for="field in readinessFields[node.readiness.type]" :key="field">
            <label v-if="field === 'require_publisher'" class="check">
              <input type="checkbox" v-model="node.readiness[field]">{{ t(`pipeline.fields.${field}`) }}
            </label>
            <label v-else class="field">{{ t(`pipeline.fields.${field}`) }}
              <input v-if="field === 'port' || field === 'delay_sec'" v-model.number="node.readiness[field]" type="number" required
                :min="field === 'port' ? 1 : 0" :max="field === 'port' ? 65535 : undefined" :step="field === 'port' ? 1 : 'any'">
              <textarea v-else-if="field === 'command'" v-model="node.readiness[field]" required rows="3" spellcheck="false" />
              <input v-else v-model="node.readiness[field]" :type="field === 'url' ? 'url' : 'text'" required spellcheck="false">
            </label>
          </template>
          <div v-if="node.readiness.type !== 'started'" class="form-pair">
            <label v-for="field in ['timeout_sec', 'interval_sec']" :key="field" class="field">
              {{ t(`pipeline.fields.${field}`) }}
              <input v-model.number="node.readiness[field]" required type="number" min="0.000001" step="any">
            </label>
          </div>
        </fieldset>
        <fieldset :disabled="ui.locked">
          <div class="form-pair">
            <label class="field">{{ t('pipeline.group') }}
              <select :value="ui.destination" @change="ui.setDestination($event.target.value)">
                <option value="">{{ t('pipeline.unassigned') }}</option>
                <option v-for="group in ui.groupOptions" :value="group.value" :key="group.value">{{ group.label }}</option>
              </select>
            </label>
            <label v-if="ui.destination" class="field">{{ t('pipeline.position') }}
              <input type="number" min="1" :max="ui.maxPosition" step="1" required v-model.number="ui.position">
            </label>
          </div>
          <label class="check"><input type="checkbox" v-model="node.enabled">{{ t('pipeline.includeNode') }}</label>
        </fieldset>
        <fieldset class="dependencies" :disabled="ui.locked">
          <legend>{{ t('pipeline.dependsOn') }}</legend>
          <div v-if="ui.dependencyOptions.length" class="dependency-list">
            <label v-for="dep in ui.dependencyOptions" :key="dep.value" class="check">
              <input type="checkbox" v-model="node.depends_on" :value="dep.value" :disabled="dep.disabled">{{ dep.label }}
            </label>
          </div>
          <p v-else class="form-hint">{{ t('pipeline.noDeps') }}</p>
        </fieldset>
        <p v-if="ui.error" class="draft-error" role="alert">{{ ui.error }}</p>
      </form>
      <template #footer>
        <NButton size="small" @click="ui.closeNode()">{{ t('common.cancel') }}</NButton>
        <NButton size="small" type="primary" form="pipeline-node-form" attr-type="submit" :disabled="ui.locked">{{ t('pipeline.apply') }}</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.dependency-list { display: grid; gap: 7px; max-height: 150px; overflow: auto; padding: 2px; }
.draft-error { margin: 0; color: v-bind('theme.errorColor'); font-size: 13px; overflow-wrap: anywhere; }
.n-button + .n-button { margin-inline-start: 8px; }
</style>
