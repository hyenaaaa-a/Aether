<template>
  <Card variant="default" class="overflow-hidden">
    <!-- 标题和筛选器 -->
    <div class="px-6 py-3.5 border-b border-border/60">
      <div class="flex items-center justify-between gap-4">
        <h3 class="text-base font-semibold">{{ title }}</h3>
        <div class="flex items-center gap-3">
          <Label class="text-xs text-muted-foreground">回溯时间：</Label>
          <Select v-model="lookbackHours" v-model:open="selectOpen">
            <SelectTrigger class="w-28 h-8 text-xs border-border/60">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 小时</SelectItem>
              <SelectItem value="6">6 小时</SelectItem>
              <SelectItem value="12">12 小时</SelectItem>
              <SelectItem value="24">24 小时</SelectItem>
              <SelectItem value="48">48 小时</SelectItem>
            </SelectContent>
          </Select>
          <RefreshButton :loading="loading" @click="refreshData" />
        </div>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="p-6">
      <div v-if="loadingMonitors" class="flex items-center justify-center py-12">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        <span class="ml-2 text-muted-foreground">加载中...</span>
      </div>

      <div v-else-if="monitors.length === 0" class="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Activity class="w-12 h-12 mb-3 opacity-30" />
        <p>暂无健康监控数据</p>
        <p class="text-xs mt-1">端点尚未产生请求记录</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="monitor in monitors"
          :key="monitor.api_format"
          class="border border-border/60 rounded-lg p-4 hover:border-primary/50 transition-colors"
        >
          <!-- 左右结构布局 -->
          <div class="flex gap-6 items-center">
            <!-- 左侧：信息区域 -->
            <div class="w-44 flex-shrink-0 space-y-1.5">
              <!-- API 格式标签和成功率 -->
              <div class="flex items-center gap-2">
                <Badge variant="outline" class="font-mono text-xs">
                  {{ monitor.api_format }}
                </Badge>
                <Badge
                  v-if="monitor.total_attempts > 0"
                  :variant="getSuccessRateVariant(monitor.success_rate)"
                  class="text-xs"
                >
                  {{ (monitor.success_rate * 100).toFixed(0) }}%
                </Badge>
              </div>

              <!-- 提供商信息（仅管理员可见） -->
              <div v-if="showProviderInfo && 'provider_count' in monitor" class="text-xs text-muted-foreground">
                {{ monitor.provider_count }} 个提供商 / {{ monitor.key_count }} 个密钥
              </div>
            </div>

            <!-- 右侧：时间线区域 -->
            <div class="flex-1 min-w-0 flex justify-end">
              <div class="w-full max-w-5xl">
                <EndpointHealthTimeline
                  :monitor="monitor"
                  :lookback-hours="parseInt(lookbackHours)"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Activity, Loader2 } from 'lucide-vue-next'
import Card from '@/components/ui/card.vue'
import Badge from '@/components/ui/badge.vue'
import Label from '@/components/ui/label.vue'
import Select from '@/components/ui/select.vue'
import SelectTrigger from '@/components/ui/select-trigger.vue'
import SelectValue from '@/components/ui/select-value.vue'
import SelectContent from '@/components/ui/select-content.vue'
import SelectItem from '@/components/ui/select-item.vue'
import RefreshButton from '@/components/ui/refresh-button.vue'
import EndpointHealthTimeline from './EndpointHealthTimeline.vue'
import { getEndpointStatusMonitor, getPublicEndpointStatusMonitor } from '@/api/endpoints/health'
import type { EndpointStatusMonitor, PublicEndpointStatusMonitor } from '@/api/endpoints/types'
import { useToast } from '@/composables/useToast'

const props = withDefaults(defineProps<{
  title?: string
  isAdmin?: boolean
  showProviderInfo?: boolean
}>(), {
  title: '健康监控',
  isAdmin: false,
  showProviderInfo: false
})

const { error: showError } = useToast()

const loading = ref(false)
const loadingMonitors = ref(false)
const monitors = ref<(EndpointStatusMonitor | PublicEndpointStatusMonitor)[]>([])
const lookbackHours = ref('6')
const selectOpen = ref(false)

async function loadMonitors() {
  loadingMonitors.value = true
  try {
    const params = {
      lookback_hours: parseInt(lookbackHours.value),
      per_format_limit: 100
    }

    if (props.isAdmin) {
      const data = await getEndpointStatusMonitor(params)
      monitors.value = data.formats || []
    } else {
      const data = await getPublicEndpointStatusMonitor(params)
      monitors.value = data.formats || []
    }
  } catch (err: any) {
    showError(err.response?.data?.detail || '加载健康监控数据失败', '错误')
  } finally {
    loadingMonitors.value = false
  }
}

async function refreshData() {
  loading.value = true
  try {
    await loadMonitors()
  } finally {
    loading.value = false
  }
}

function getSuccessRateVariant(rate: number): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (rate >= 0.95) return 'default'
  if (rate >= 0.8) return 'secondary'
  return 'destructive'
}

watch(lookbackHours, () => {
  loadMonitors()
})

onMounted(() => {
  refreshData()
})
</script>
