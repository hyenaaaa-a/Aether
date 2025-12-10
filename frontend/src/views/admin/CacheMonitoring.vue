<script setup lang="ts">
import { ref, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import Card from '@/components/ui/card.vue'
import Button from '@/components/ui/button.vue'
import Badge from '@/components/ui/badge.vue'
import Table from '@/components/ui/table.vue'
import TableBody from '@/components/ui/table-body.vue'
import TableCell from '@/components/ui/table-cell.vue'
import TableHead from '@/components/ui/table-head.vue'
import TableHeader from '@/components/ui/table-header.vue'
import TableRow from '@/components/ui/table-row.vue'
import Input from '@/components/ui/input.vue'
import Pagination from '@/components/ui/pagination.vue'
import RefreshButton from '@/components/ui/refresh-button.vue'
import { Trash2, Eraser, Search, X } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { cacheApi, type CacheStats, type CacheConfig, type UserAffinity } from '@/api/cache'

const stats = ref<CacheStats | null>(null)
const config = ref<CacheConfig | null>(null)
const loading = ref(false)
const affinityList = ref<UserAffinity[]>([])
const listLoading = ref(false)
const tableKeyword = ref('')
const matchedUserId = ref<string | null>(null)
const clearingRowAffinityKey = ref<string | null>(null)
const currentPage = ref(1)
const pageSize = ref(20)
const { success: showSuccess, error: showError, info: showInfo } = useToast()
const { confirm: showConfirm } = useConfirm()
const currentTime = ref(Math.floor(Date.now() / 1000))

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null
let skipNextKeywordWatch = false
let countdownTimer: ReturnType<typeof setInterval> | null = null

// 计算分页后的数据
const paginatedAffinityList = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return affinityList.value.slice(start, end)
})

// 页码变化处理
function handlePageChange() {
  // 分页变化时滚动到顶部
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// 获取缓存统计
async function fetchCacheStats() {
  loading.value = true
  try {
    stats.value = await cacheApi.getStats()
  } catch (error) {
    showError('获取缓存统计失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 获取缓存配置
async function fetchCacheConfig() {
  try {
    config.value = await cacheApi.getConfig()
  } catch (error) {
    console.error(error)
  }
}

// 获取缓存亲和性列表
async function fetchAffinityList(keyword?: string) {
  listLoading.value = true
  try {
    const response = await cacheApi.listAffinities(keyword)
    affinityList.value = response.items
    matchedUserId.value = response.matched_user_id ?? null

    if (keyword && response.total === 0) {
      showInfo('未找到匹配的缓存记录')
    }
  } catch (error) {
    showError('获取缓存列表失败')
    console.error(error)
  } finally {
    listLoading.value = false
  }
}

async function resetAffinitySearch() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }

  if (!tableKeyword.value) {
    currentPage.value = 1
    await fetchAffinityList()
    return
  }

  skipNextKeywordWatch = true
  tableKeyword.value = ''
  currentPage.value = 1
  await fetchAffinityList()
}

// 清除缓存（按 affinity_key 或用户标识符）
async function clearUserCache(identifier: string, displayName?: string) {
  const target = identifier?.trim()

  if (!target) {
    showError('无法识别标识符')
    return
  }

  const label = displayName || target

  const confirmed = await showConfirm({
    title: '确认清除',
    message: `确定要清除 ${label} 的缓存吗？`,
    confirmText: '确认清除',
    variant: 'destructive'
  })

  if (!confirmed) {
    return
  }

  clearingRowAffinityKey.value = target

  try {
    await cacheApi.clearUserCache(target)
    showSuccess('清除成功')
    await fetchCacheStats()
    await fetchAffinityList(tableKeyword.value.trim() || undefined)
  } catch (error) {
    showError('清除失败')
    console.error(error)
  } finally {
    clearingRowAffinityKey.value = null
  }
}

// 清除所有缓存
async function clearAllCache() {
  const firstConfirm = await showConfirm({
    title: '危险操作',
    message: '警告：此操作会清除所有用户的缓存亲和性，确定继续吗？',
    confirmText: '继续',
    variant: 'destructive'
  })

  if (!firstConfirm) {
    return
  }

  const secondConfirm = await showConfirm({
    title: '再次确认',
    message: '这将影响所有用户，请再次确认！',
    confirmText: '确认清除',
    variant: 'destructive'
  })

  if (!secondConfirm) {
    return
  }

  try {
    await cacheApi.clearAllCache()
    showSuccess('已清除所有缓存')
    await fetchCacheStats()
    await fetchAffinityList(tableKeyword.value.trim() || undefined)
  } catch (error) {
    showError('清除失败')
    console.error(error)
  }
}

// 计算剩余时间（使用实时更新的 currentTime）
function getRemainingTime(expireAt?: number) {
  if (!expireAt) return '未知'
  const remaining = expireAt - currentTime.value
  if (remaining <= 0) return '已过期'

  const minutes = Math.floor(remaining / 60)
  const seconds = Math.floor(remaining % 60)
  return `${minutes}分${seconds}秒`
}

// 启动倒计时定时器
function startCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
  }

  countdownTimer = setInterval(() => {
    currentTime.value = Math.floor(Date.now() / 1000)

    // 过滤掉已过期的项目
    const beforeCount = affinityList.value.length
    affinityList.value = affinityList.value.filter(item => {
      return item.expire_at && item.expire_at > currentTime.value
    })

    // 如果有项目被移除，显示提示
    if (beforeCount > affinityList.value.length) {
      const removedCount = beforeCount - affinityList.value.length
      showInfo(`${removedCount} 个缓存已自动过期移除`)
    }
  }, 1000)
}

// 停止倒计时定时器
function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

watch(tableKeyword, (value) => {
  if (skipNextKeywordWatch) {
    skipNextKeywordWatch = false
    return
  }

  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }

  const keyword = value.trim()
  searchDebounceTimer = setTimeout(() => {
    fetchAffinityList(keyword || undefined)
    searchDebounceTimer = null
  }, 600)
})

onMounted(() => {
  fetchCacheStats()
  fetchCacheConfig()
  fetchAffinityList()
  startCountdown()
})

// 刷新所有数据
async function refreshData() {
  await Promise.all([
    fetchCacheStats(),
    fetchCacheConfig(),
    fetchAffinityList()
  ])
}

onBeforeUnmount(() => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  stopCountdown()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div>
      <h2 class="text-2xl font-bold">缓存监控</h2>
      <p class="text-sm text-muted-foreground mt-1">
        管理缓存亲和性，提高 Prompt Caching 命中率
      </p>
    </div>

    <!-- 核心指标 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <!-- 缓存命中率 -->
      <Card class="p-4">
        <div class="text-xs text-muted-foreground">命中率</div>
        <div class="text-2xl font-bold text-success mt-1">
          {{ stats ? (stats.affinity_stats.cache_hit_rate * 100).toFixed(1) : '0.0' }}%
        </div>
        <div class="text-xs text-muted-foreground mt-1">
          {{ stats?.affinity_stats?.cache_hits || 0 }} / {{ (stats?.affinity_stats?.cache_hits || 0) + (stats?.affinity_stats?.cache_misses || 0) }}
        </div>
      </Card>

      <!-- 活跃缓存数 -->
      <Card class="p-4">
        <div class="text-xs text-muted-foreground">活跃缓存</div>
        <div class="text-2xl font-bold mt-1">
          {{ stats?.affinity_stats?.total_affinities || 0 }}
        </div>
        <div class="text-xs text-muted-foreground mt-1">
          TTL {{ config?.cache_ttl_seconds || 300 }}s
        </div>
      </Card>

      <!-- Provider切换 -->
      <Card class="p-4">
        <div class="text-xs text-muted-foreground">Provider 切换</div>
        <div class="text-2xl font-bold mt-1" :class="(stats?.affinity_stats?.provider_switches || 0) > 0 ? 'text-destructive' : ''">
          {{ stats?.affinity_stats?.provider_switches || 0 }}
        </div>
        <div class="text-xs text-muted-foreground mt-1">
          Key 切换 {{ stats?.affinity_stats?.key_switches || 0 }}
        </div>
      </Card>

      <!-- 预留比例 -->
      <Card class="p-4">
        <div class="text-xs text-muted-foreground flex items-center gap-1">
          预留比例
          <Badge v-if="config?.dynamic_reservation?.enabled" variant="outline" class="text-[10px] px-1">动态</Badge>
        </div>
        <div class="text-2xl font-bold mt-1">
          <template v-if="config?.dynamic_reservation?.enabled">
            {{ (config.dynamic_reservation.config.stable_min_reservation * 100).toFixed(0) }}-{{ (config.dynamic_reservation.config.stable_max_reservation * 100).toFixed(0) }}%
          </template>
          <template v-else>
            {{ config ? (config.cache_reservation_ratio * 100).toFixed(0) : '30' }}%
          </template>
        </div>
        <div class="text-xs text-muted-foreground mt-1">
          失效 {{ stats?.affinity_stats?.cache_invalidations || 0 }}
        </div>
      </Card>
    </div>

    <!-- 缓存亲和性列表 -->
    <Card class="overflow-hidden">
      <!-- 标题和操作栏 -->
      <div class="px-6 py-3 border-b border-border/60">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <h3 class="text-base font-semibold">亲和性列表</h3>
          </div>
          <div class="flex items-center gap-2">
            <div class="relative">
              <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground z-10 pointer-events-none" />
              <Input
                id="cache-affinity-search"
                v-model="tableKeyword"
                placeholder="搜索用户或 Key"
                class="w-48 h-8 text-sm pl-8 pr-8"
              />
              <button
                v-if="tableKeyword"
                type="button"
                class="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground z-10"
                @click="resetAffinitySearch"
              >
                <X class="h-3.5 w-3.5" />
              </button>
            </div>
            <div class="h-4 w-px bg-border" />
            <Button @click="clearAllCache" variant="ghost" size="icon" class="h-8 w-8 text-muted-foreground/70 hover:text-destructive" title="清除全部缓存">
              <Eraser class="h-4 w-4" />
            </Button>
            <RefreshButton :loading="loading || listLoading" @click="refreshData" />
          </div>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead class="w-28">用户</TableHead>
            <TableHead class="w-36">Key</TableHead>
            <TableHead class="w-28">Provider</TableHead>
            <TableHead class="w-40">模型</TableHead>
            <TableHead class="w-36">API 格式 / Key</TableHead>
            <TableHead class="w-20 text-center">剩余</TableHead>
            <TableHead class="w-14 text-center">次数</TableHead>
            <TableHead class="w-12 text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody v-if="!listLoading && affinityList.length">
          <TableRow v-for="item in paginatedAffinityList" :key="`${item.affinity_key}-${item.endpoint_id}-${item.key_id}`">
            <TableCell>
              <div class="flex items-center gap-1.5">
                <Badge v-if="item.is_standalone" variant="outline" class="text-warning border-warning/30 text-[10px] px-1">独立</Badge>
                <span class="text-sm font-medium truncate max-w-[90px]" :title="item.username ?? undefined">{{ item.username || '未知' }}</span>
              </div>
            </TableCell>
            <TableCell>
              <div class="flex items-center gap-1.5">
                <span class="text-sm truncate max-w-[100px]" :title="item.user_api_key_name || undefined">{{ item.user_api_key_name || '未命名' }}</span>
                <Badge v-if="item.rate_multiplier !== 1.0" variant="outline" class="text-warning border-warning/30 text-[10px] px-2">{{ item.rate_multiplier }}x</Badge>
              </div>
              <div class="text-xs text-muted-foreground font-mono">{{ item.user_api_key_prefix || '---' }}</div>
            </TableCell>
            <TableCell>
              <div class="text-sm truncate max-w-[100px]" :title="item.provider_name || undefined">{{ item.provider_name || '未知' }}</div>
            </TableCell>
            <TableCell>
              <div class="text-sm truncate max-w-[150px]" :title="item.model_display_name || undefined">{{ item.model_display_name || '---' }}</div>
              <div class="text-xs text-muted-foreground" :title="item.model_name || undefined">{{ item.model_name || '---' }}</div>
            </TableCell>
            <TableCell>
              <div class="text-sm">{{ item.endpoint_api_format || '---' }}</div>
              <div class="text-xs text-muted-foreground font-mono">{{ item.key_prefix || '---' }}</div>
            </TableCell>
            <TableCell class="text-center">
              <span class="text-xs">{{ getRemainingTime(item.expire_at) }}</span>
            </TableCell>
            <TableCell class="text-center">
              <span class="text-sm">{{ item.request_count }}</span>
            </TableCell>
            <TableCell class="text-right">
              <Button
                size="icon"
                variant="ghost"
                class="h-7 w-7 text-muted-foreground/70 hover:text-destructive"
                @click="clearUserCache(item.affinity_key, item.user_api_key_name || item.affinity_key)"
                :disabled="clearingRowAffinityKey === item.affinity_key"
                title="清除缓存"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
        <TableBody v-else>
          <TableRow>
            <TableCell colspan="8" class="text-center py-6 text-sm text-muted-foreground">
              {{ listLoading ? '加载中...' : '暂无缓存记录' }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <Pagination
        v-if="affinityList.length > 0"
        :current="currentPage"
        :total="affinityList.length"
        :page-size="pageSize"
        @update:current="currentPage = $event; handlePageChange()"
        @update:page-size="pageSize = $event"
      />
    </Card>
  </div>
</template>
