<template>
  <Card class="overflow-hidden">
    <!-- 标题和操作栏 -->
    <div v-if="$slots.header || title" class="px-6 py-3.5 border-b border-border/60">
      <slot name="header">
        <div class="flex items-center justify-between gap-4">
          <!-- 左侧：标题 -->
          <h3 class="text-base font-semibold">{{ title }}</h3>

          <!-- 右侧：操作区 -->
          <div v-if="$slots.actions" class="flex items-center gap-2">
            <slot name="actions" />
          </div>
        </div>
      </slot>
    </div>

    <!-- 表格内容 -->
    <slot />

    <!-- 分页 -->
    <slot name="pagination" />
  </Card>
</template>

<script setup lang="ts">
import { Card } from '@/components/ui'

interface Props {
  title?: string
}

defineProps<Props>()
</script>
