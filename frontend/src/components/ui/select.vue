<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { SelectRoot as SelectRootPrimitive } from 'radix-vue'

interface Props {
  defaultValue?: string
  modelValue?: string
  open?: boolean
  defaultOpen?: boolean
  dir?: 'ltr' | 'rtl'
  name?: string
  autocomplete?: string
  disabled?: boolean
  required?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:open': [value: boolean]
}>()

const internalValue = ref<string | undefined>(
  props.modelValue ?? props.defaultValue
)

const isModelControlled = computed(() => props.modelValue !== undefined)

watch(
  () => props.modelValue,
  value => {
    if (isModelControlled.value) {
      internalValue.value = value
    }
  }
)

const modelValueState = computed({
  get: () => (isModelControlled.value ? props.modelValue : internalValue.value),
  set: (value: string | undefined) => {
    if (!isModelControlled.value) {
      internalValue.value = value
    }
    // Cast to string for the emit signature when value exists
    if (value !== undefined) {
      emit('update:modelValue', value)
    }
  }
})

const internalOpen = ref<boolean>(
  props.open ?? props.defaultOpen ?? false
)

const isOpenControlled = computed(() => props.open !== undefined)

watch(
  () => props.open,
  value => {
    if (isOpenControlled.value && value !== undefined) {
      internalOpen.value = value
    }
  }
)

const openState = computed({
  get: () => (isOpenControlled.value ? props.open : internalOpen.value),
  set: (value: boolean) => {
    if (!isOpenControlled.value) {
      internalOpen.value = value
    }
    emit('update:open', value)
  }
})
</script>

<template>
  <SelectRootPrimitive
    :default-value="defaultValue"
    :model-value="modelValueState"
    :open="openState"
    :default-open="defaultOpen"
    :dir="dir"
    :name="name"
    :autocomplete="autocomplete"
    :disabled="disabled"
    :required="required"
    @update:model-value="modelValueState = $event"
    @update:open="openState = $event"
  >
    <slot />
  </SelectRootPrimitive>
</template>
