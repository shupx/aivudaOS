<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function onChange(event) {
  const requested = event.target.checked
  // The parent may require confirmation before accepting a change.
  event.target.checked = props.modelValue
  emit('update:modelValue', requested)
}
</script>

<template>
  <label class="switch" :class="{ disabled }">
    <input :checked="modelValue" type="checkbox" :disabled="disabled" @change="onChange" />
    <span class="slider"></span>
  </label>
</template>
