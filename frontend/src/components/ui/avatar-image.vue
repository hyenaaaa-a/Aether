<script setup lang="ts">
import { AvatarImage as AvatarImagePrimitive } from 'radix-vue'
import { cn } from '@/lib/utils'
import { computed } from 'vue'

interface Props {
  class?: string
  src?: string
  alt: string
}

const props = withDefaults(defineProps<Props>(), {
  alt: ''
})

const imageClass = computed(() =>
  cn('aspect-square h-full w-full', props.class)
)
</script>

<template>
  <AvatarImagePrimitive :class="imageClass" :src="src || ''" :alt="alt" />
</template>
