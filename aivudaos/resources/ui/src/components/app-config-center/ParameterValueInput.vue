<script setup>
import { NAutoComplete } from 'naive-ui'
import { useParameterValueInput } from '../../composables/useParameterValueInput'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  value: { type: [String, Number], default: '' },
  historyKey: { type: String, default: '' },
  commit: { type: Function, required: true },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
})
const emit = defineEmits(['update:value'])
const { options, onInput, onFocus, onSelect, commitValue } = useParameterValueInput(props, emit)
</script>

<template>
  <NAutoComplete
    class="parameter-value-input"
    :value="String(value ?? '')"
    :options="options"
    :disabled="disabled"
    :get-show="() => options.length > 0"
    @update:value="onInput"
    @focus="onFocus"
    @blur="commitValue"
    @select="onSelect"
    @keyup.enter="!$event.isComposing && commitValue()"
  >
    <template #default="{ handleInput, handleFocus, handleBlur, value: inputValue }">
      <input
        v-bind="$attrs"
        class="input"
        :type="type"
        :disabled="disabled"
        :placeholder="placeholder"
        :value="inputValue"
        :name="historyKey ? `parameter-${historyKey}` : undefined"
        autocomplete="off"
        @input="handleInput($event.target.value)"
        @focus="handleFocus"
        @blur="handleBlur"
      >
    </template>
  </NAutoComplete>
</template>

<style scoped>
.parameter-value-input {
  width: 100%;
}
</style>
