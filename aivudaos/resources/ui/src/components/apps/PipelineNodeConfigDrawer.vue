<script setup>
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NFormItem, NInput, NInputNumber, NSelect, NSwitch, NText } from 'naive-ui'
import { readinessFields } from '../../services/core/startupPipeline.js'

defineProps({ node: Object, destination: String, position: Number, maxPosition: Number, groups: Array, dependencies: Array, probes: Array, name: String })
const emit = defineEmits(['close', 'apply', 'change-probe', 'update:destination', 'update:position'])
const { t } = useI18n()
</script>

<template>
  <NDrawer :show="Boolean(node)" placement="right" width="min(420px, 100vw)" @update:show="emit('close')">
    <NDrawerContent v-if="node" :title="t('pipeline.configureNode')" closable>
      <h3>{{ name }}</h3><NText depth="3">{{ node.app_id }}</NText>
      <form class="probe-form" @submit.prevent="emit('apply')" id="pipeline-node-form">
        <NFormItem :label="t('pipeline.stage')">
          <NSelect :value="destination" :options="[{ value: '', label: t('pipeline.unassigned') }, ...groups]"
            @update:value="emit('update:destination', $event)" />
        </NFormItem>
        <NFormItem v-if="destination" :label="t('pipeline.position')">
          <NInputNumber :value="position" :min="1" :max="maxPosition" :precision="0" @update:value="emit('update:position', $event)" />
        </NFormItem>
        <NFormItem :label="t('pipeline.includeNode')"><NSwitch v-model:value="node.enabled" :aria-label="t('pipeline.includeNode')" /></NFormItem>
        <NFormItem :label="t('pipeline.dependsOn')">
          <NSelect v-model:value="node.depends_on" multiple filterable clearable :options="dependencies" :placeholder="t('pipeline.noDeps')" />
        </NFormItem>
        <h4>{{ t('pipeline.readiness') }}</h4>
        <NFormItem :label="t('pipeline.probeType')">
          <NSelect :value="node.readiness.type" :options="probes" @update:value="emit('change-probe', $event)" />
        </NFormItem>
        <NFormItem v-for="field in readinessFields[node.readiness.type]" :key="field" :label="t(`pipeline.fields.${field}`)">
          <NInputNumber v-if="field === 'delay_sec' || field === 'port'" v-model:value="node.readiness[field]"
            :min="field === 'port' ? 1 : 0" :max="field === 'port' ? 65535 : undefined" :precision="field === 'port' ? 0 : undefined" />
          <NSwitch v-else-if="field === 'require_publisher'" v-model:value="node.readiness[field]" :aria-label="t(`pipeline.fields.${field}`)" />
          <NInput v-else v-model:value="node.readiness[field]" :type="field === 'command' ? 'textarea' : 'text'" />
        </NFormItem>
        <template v-if="node.readiness.type !== 'started'">
          <NFormItem v-for="field in ['timeout_sec', 'interval_sec']" :key="field" :label="t(`pipeline.fields.${field}`)">
            <NInputNumber v-model:value="node.readiness[field]" :min="0.01" /></NFormItem>
        </template>
      </form>
      <template #footer>
        <div class="drawer-actions"><NButton @click="emit('close')">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" attr-type="submit" form="pipeline-node-form">{{ t('pipeline.apply') }}</NButton></div>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.probe-form { margin-top: 22px; }
.probe-form h4 { margin: 0 0 14px; }
.drawer-actions { display: flex; gap: 8px; }
</style>
