<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  magnets: { type: Array, default: () => [] },
  magnetConflicts: { type: Array, default: () => [] },
  getMagnetValue: { type: Function, required: true },
  getMagnetDisplayValue: { type: Function, required: true },
  onMagnetBooleanChange: { type: Function, required: true },
  onMagnetTextChange: { type: Function, required: true },
  saveMagnetChanges: { type: Function, required: true },
  valueToInlineText: { type: Function, required: true },
})
</script>

<template>
  <article class="actions-panel">
    <header class="log-header">
      <h3>{{ t('appConfigCenter.magnetTitle') }}</h3>
    </header>

    <div v-if="!magnets.length" class="empty-box">{{ t('appConfigCenter.magnetEmpty') }}</div>
    <div v-else class="table-wrap">
      <table class="config-table compact">
        <thead>
          <tr>
            <th>{{ t('appConfigCenter.colPath') }}</th>
            <th>{{ t('appConfigCenter.colCurrent') }}</th>
            <th>{{ t('appConfigCenter.colType') }}</th>
            <th>{{ t('appConfigCenter.magnetBindings') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in magnets" :key="group.group_id">
            <td class="mono-cell">{{ group.path }}</td>
            <td>
              <label v-if="group.value_type === 'boolean'" class="check-item">
                <input
                  :checked="Boolean(getMagnetValue(group))"
                  type="checkbox"
                  @change="onMagnetBooleanChange(group, $event?.target?.checked); saveMagnetChanges(group)"
                >
                {{ Boolean(getMagnetValue(group)) ? 'true' : 'false' }}
              </label>
              <input
                v-else
                class="input"
                :value="getMagnetDisplayValue(group)"
                @change="onMagnetTextChange(group, $event?.target?.value || ''); saveMagnetChanges(group)"
              >
            </td>
            <td>{{ group.value_type || '-' }}</td>
            <td class="mono-cell">{{ valueToInlineText(group.bindings || []) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="magnetConflicts.length" class="error-text">{{ t('appConfigCenter.magnetConflictsHint') }}</p>
  </article>
</template>
