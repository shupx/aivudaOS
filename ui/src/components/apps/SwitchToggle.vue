<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function onChange(event) {
  emit('update:modelValue', event.target.checked)
}
</script>

<template>
  <label class="switch" :class="{ disabled }">
    <input :checked="modelValue" type="checkbox" :disabled="disabled" @change="onChange" />
    <span class="slider"></span>
  </label>
</template>
