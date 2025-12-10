<template>
  <input
    :class="inputClass"
    :value="modelValue"
    :autocomplete="autocompleteAttr"
    v-bind="$attrs"
    @input="handleInput"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  modelValue?: string | number
  class?: string
  autocomplete?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const autocompleteAttr = computed(() => props.autocomplete ?? 'off')

const inputClass = computed(() =>
  cn(
    'flex h-11 w-full rounded-2xl border border-border/60 bg-card/80 px-4 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 text-foreground backdrop-blur transition-all',
    props.class
  )
)

function handleInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>
