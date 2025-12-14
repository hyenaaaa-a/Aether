<template>
  <Dialog
    :model-value="open"
    title="拉取远程模型"
    description="从 Provider 的 API 获取可用模型列表并导入"
    :icon="CloudDownload"
    size="xl"
    @update:model-value="handleClose"
  >
    <div class="space-y-4">
      <!-- 加载状态 -->
      <div
        v-if="loading"
        class="flex flex-col items-center justify-center py-8"
      >
        <Loader2 class="w-8 h-8 animate-spin text-primary mb-3" />
        <p class="text-sm text-muted-foreground">
          正在从远程 API 获取模型列表...
        </p>
      </div>

      <!-- 错误状态 -->
      <div
        v-else-if="errorMessage"
        class="flex flex-col items-center justify-center py-8"
      >
        <AlertCircle class="w-12 h-12 text-destructive mb-3" />
        <p class="text-sm text-destructive text-center mb-4">
          {{ errorMessage }}
        </p>
        <Button
          variant="outline"
          @click="fetchModels"
        >
          重试
        </Button>
      </div>

      <!-- 模型列表 -->
      <div
        v-else-if="remoteModels.length > 0"
        class="space-y-4"
      >
        <!-- 端点信息 -->
        <div class="text-xs text-muted-foreground bg-muted/50 rounded-md p-2">
          <span>从端点获取：</span>
          <span class="font-mono">{{ endpointBaseUrl }}</span>
        </div>

        <!-- 搜索框 -->
        <div class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索模型 ID..."
            class="w-full h-9 pl-9 pr-3 rounded-md border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
        </div>

        <!-- 全选操作 -->
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              v-model="selectAll"
              type="checkbox"
              class="rounded"
              @change="handleSelectAll"
            >
            <span class="text-sm">全选筛选结果 ({{ filteredModels.length }} / {{ remoteModels.length }} 个)</span>
          </label>
          <span class="text-sm text-muted-foreground">
            已选择 {{ selectedModels.size }} 个
          </span>
        </div>

        <!-- 模型列表 -->
        <div class="max-h-[400px] overflow-y-auto border rounded-md">
          <table class="w-full text-sm">
            <thead class="bg-muted/50 sticky top-0">
              <tr>
                <th class="w-12 px-3 py-2"></th>
                <th class="text-left px-3 py-2 font-medium">模型 ID</th>
                <th class="text-left px-3 py-2 font-medium">预计别名</th>
                <th class="text-left px-3 py-2 font-medium">所有者</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border/40">
              <tr
                v-for="model in filteredModels"
                :key="model.id"
                class="hover:bg-muted/30 transition-colors"
                :class="{
                  'bg-primary/5': selectedModels.has(model.id),
                  'opacity-50': existingModels.has(model.id)
                }"
              >
                <td class="px-3 py-2 text-center">
                  <input
                    :checked="selectedModels.has(model.id)"
                    type="checkbox"
                    class="rounded"
                    :disabled="existingModels.has(model.id)"
                    @change="toggleModel(model.id)"
                  >
                </td>
                <td class="px-3 py-2 font-mono">
                  {{ model.id }}
                  <Badge
                    v-if="existingModels.has(model.id)"
                    variant="secondary"
                    class="ml-2 text-[10px]"
                  >
                    已存在
                  </Badge>
                </td>
                <td class="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {{ getExpectedAlias(model.id) }}
                </td>
                <td class="px-3 py-2 text-muted-foreground">
                  {{ model.owned_by || '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-else
        class="flex flex-col items-center justify-center py-8"
      >
        <Box class="w-12 h-12 text-muted-foreground/50 mb-3" />
        <p class="text-sm text-muted-foreground">
          未获取到任何模型
        </p>
      </div>
    </div>

    <template #footer>
      <Button
        variant="outline"
        @click="handleClose(false)"
      >
        取消
      </Button>
      <Button
        :disabled="selectedModels.size === 0 || importing"
        @click="handleImport"
      >
        <Loader2
          v-if="importing"
          class="w-4 h-4 mr-2 animate-spin"
        />
        导入 {{ selectedModels.size }} 个模型
      </Button>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { CloudDownload, Loader2, AlertCircle, Box, Search } from 'lucide-vue-next'
import { Dialog, Button, Badge } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import {
  fetchRemoteModels,
  importRemoteModels,
  getProviderModels,
  type RemoteModelItem
} from '@/api/endpoints/models'

interface Props {
  open: boolean
  providerId: string
  providerName?: string
  providerIdentifier?: string  // provider.name 用于构建别名
}

const props = withDefaults(defineProps<Props>(), {
  providerName: '',
  providerIdentifier: ''
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  'imported': []
}>()

const { error: showError, success: showSuccess } = useToast()

// 状态
const loading = ref(false)
const importing = ref(false)
const errorMessage = ref('')
const remoteModels = ref<RemoteModelItem[]>([])
const endpointBaseUrl = ref('')
const selectedModels = ref<Set<string>>(new Set())
const existingModels = ref<Set<string>>(new Set())
const searchQuery = ref('')

// 筛选后的模型列表
const filteredModels = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  if (!query) return remoteModels.value
  return remoteModels.value.filter(m => 
    m.id.toLowerCase().includes(query) ||
    (m.owned_by && m.owned_by.toLowerCase().includes(query))
  )
})

// 全选状态（基于筛选后的列表）
const selectAll = computed({
  get: () => {
    const selectable = filteredModels.value.filter(m => !existingModels.value.has(m.id))
    return selectable.length > 0 && selectable.every(m => selectedModels.value.has(m.id))
  },
  set: () => {}
})

// 监听 open 变化
watch(() => props.open, async (newOpen) => {
  if (newOpen) {
    resetState()
    await fetchModels()
  }
})

// 重置状态
function resetState() {
  loading.value = false
  importing.value = false
  errorMessage.value = ''
  remoteModels.value = []
  endpointBaseUrl.value = ''
  selectedModels.value = new Set()
  existingModels.value = new Set()
  searchQuery.value = ''
}

// 计算预计别名
function getExpectedAlias(modelId: string): string {
  return props.providerIdentifier ? `${props.providerIdentifier}/${modelId}` : modelId
}

// 获取远程模型
async function fetchModels() {
  loading.value = true
  errorMessage.value = ''

  try {
    // 并行获取远程模型和已有模型
    const [remoteResponse, existingResponse] = await Promise.all([
      fetchRemoteModels(props.providerId),
      getProviderModels(props.providerId)
    ])

    remoteModels.value = remoteResponse.models
    endpointBaseUrl.value = remoteResponse.endpoint_base_url

    // 标记已存在的模型
    existingModels.value = new Set(
      existingResponse.map(m => m.provider_model_name)
    )
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.message || '获取模型列表失败'
  } finally {
    loading.value = false
  }
}

// 切换模型选中状态
function toggleModel(modelId: string) {
  if (existingModels.value.has(modelId)) return

  const newSet = new Set(selectedModels.value)
  if (newSet.has(modelId)) {
    newSet.delete(modelId)
  } else {
    newSet.add(modelId)
  }
  selectedModels.value = newSet
}

// 全选/取消全选（基于筛选后的列表）
function handleSelectAll() {
  const selectable = filteredModels.value.filter(m => !existingModels.value.has(m.id))
  
  if (selectAll.value) {
    // 已全选，取消全选
    selectable.forEach(m => selectedModels.value.delete(m.id))
    selectedModels.value = new Set(selectedModels.value)
  } else {
    // 未全选，全选
    const newSet = new Set(selectedModels.value)
    selectable.forEach(m => newSet.add(m.id))
    selectedModels.value = newSet
  }
}

// 导入模型
async function handleImport() {
  if (selectedModels.value.size === 0) return

  importing.value = true
  try {
    const result = await importRemoteModels(
      props.providerId,
      Array.from(selectedModels.value)
    )

    if (result.success.length > 0) {
      showSuccess(`成功导入 ${result.success.length} 个模型`)
    }

    if (result.errors.length > 0) {
      showError(`${result.errors.length} 个模型导入失败`, '部分失败')
    }

    emit('update:open', false)
    emit('imported')
  } catch (err: any) {
    showError(err.response?.data?.detail || err.message || '导入失败', '错误')
  } finally {
    importing.value = false
  }
}

// 关闭对话框
function handleClose(value: boolean) {
  if (!loading.value && !importing.value) {
    emit('update:open', value)
  }
}
</script>
