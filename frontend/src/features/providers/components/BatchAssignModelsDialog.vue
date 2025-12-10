<template>
  <Dialog
    :model-value="open"
    @update:model-value="$emit('update:open', $event)"
    title="批量添加关联模型"
    description="为提供商批量添加模型实现，提供商将自动继承模型的价格和能力，可在添加后单独修改"
    :icon="Layers"
    size="4xl"
  >
    <template #default>
      <div class="space-y-4">
        <!-- 提供商信息头部 -->
        <div class="rounded-lg border bg-muted/30 p-4">
          <div class="flex items-start justify-between">
            <div>
              <p class="font-semibold text-lg">{{ providerName }}</p>
              <p class="text-sm text-muted-foreground font-mono">{{ providerIdentifier }}</p>
            </div>
            <Badge variant="outline" class="text-xs">
              当前 {{ existingModels.length }} 个模型
            </Badge>
          </div>
        </div>

        <!-- 左右对比布局 -->
        <div class="flex gap-2 items-stretch">
          <!-- 左侧：可添加的模型 -->
          <div class="flex-1 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">可添加</p>
                <Button
                  v-if="availableModels.length > 0"
                  variant="ghost"
                  size="sm"
                  class="h-6 px-2 text-xs"
                  @click="toggleSelectAllLeft"
                >
                  {{ isAllLeftSelected ? '取消全选' : '全选' }}
                </Button>
              </div>
              <Badge variant="secondary" class="text-xs">
                {{ availableModels.length }} 个
              </Badge>
            </div>
            <div class="border rounded-lg h-80 overflow-y-auto">
              <div v-if="loadingGlobalModels" class="flex items-center justify-center h-full">
                <Loader2 class="w-6 h-6 animate-spin text-primary" />
              </div>
              <div v-else-if="availableModels.length === 0" class="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Layers class="w-10 h-10 mb-2 opacity-30" />
                <p class="text-sm">所有模型均已关联</p>
              </div>
              <div v-else class="p-2 space-y-1">
                <div
                  v-for="model in availableModels"
                  :key="model.id"
                  class="flex items-center gap-2 p-2 rounded-lg border transition-colors"
                  :class="selectedLeftIds.includes(model.id)
                    ? 'border-primary bg-primary/10'
                    : 'hover:bg-muted/50 cursor-pointer'"
                  @click="toggleLeftSelection(model.id)"
                >
                  <Checkbox
                    :checked="selectedLeftIds.includes(model.id)"
                    @update:checked="toggleLeftSelection(model.id)"
                    @click.stop
                  />
                  <div class="flex-1 min-w-0">
                    <p class="font-medium text-sm truncate">{{ model.display_name }}</p>
                    <p class="text-xs text-muted-foreground truncate font-mono">{{ model.name }}</p>
                  </div>
                  <Badge
                    :variant="model.is_active ? 'outline' : 'secondary'"
                    :class="model.is_active ? 'text-green-600 border-green-500/60' : ''"
                    class="text-xs shrink-0"
                  >
                    {{ model.is_active ? '活跃' : '停用' }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <!-- 中间：操作按钮 -->
          <div class="flex flex-col items-center justify-center w-12 shrink-0 gap-2">
            <Button
              variant="outline"
              size="sm"
              class="w-9 h-8"
              :class="selectedLeftIds.length > 0 && !submittingAdd ? 'border-primary' : ''"
              :disabled="selectedLeftIds.length === 0 || submittingAdd"
              @click="batchAddSelected"
              title="添加选中"
            >
              <Loader2 v-if="submittingAdd" class="w-4 h-4 animate-spin" />
              <ChevronRight v-else class="w-6 h-6 stroke-[3]" :class="selectedLeftIds.length > 0 && !submittingAdd ? 'text-primary' : ''" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              class="w-9 h-8"
              :class="selectedRightIds.length > 0 && !submittingRemove ? 'border-primary' : ''"
              :disabled="selectedRightIds.length === 0 || submittingRemove"
              @click="batchRemoveSelected"
              title="移除选中"
            >
              <Loader2 v-if="submittingRemove" class="w-4 h-4 animate-spin" />
              <ChevronLeft v-else class="w-6 h-6 stroke-[3]" :class="selectedRightIds.length > 0 && !submittingRemove ? 'text-primary' : ''" />
            </Button>
          </div>

          <!-- 右侧：已添加的模型 -->
          <div class="flex-1 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">已添加</p>
                <Button
                  v-if="existingModels.length > 0"
                  variant="ghost"
                  size="sm"
                  class="h-6 px-2 text-xs"
                  @click="toggleSelectAllRight"
                >
                  {{ isAllRightSelected ? '取消全选' : '全选' }}
                </Button>
              </div>
              <Badge variant="secondary" class="text-xs">
                {{ existingModels.length }} 个
              </Badge>
            </div>
            <div class="border rounded-lg h-80 overflow-y-auto">
              <div v-if="existingModels.length === 0" class="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Layers class="w-10 h-10 mb-2 opacity-30" />
                <p class="text-sm">暂无关联模型</p>
              </div>
              <div v-else class="p-2 space-y-1">
                <div
                  v-for="model in existingModels"
                  :key="'existing-' + model.id"
                  class="flex items-center gap-2 p-2 rounded-lg border transition-colors cursor-pointer"
                  :class="selectedRightIds.includes(model.id)
                    ? 'border-primary bg-primary/10'
                    : 'hover:bg-muted/50'"
                  @click="toggleRightSelection(model.id)"
                >
                  <Checkbox
                    :checked="selectedRightIds.includes(model.id)"
                    @update:checked="toggleRightSelection(model.id)"
                    @click.stop
                  />
                  <div class="flex-1 min-w-0">
                    <p class="font-medium text-sm truncate">{{ model.global_model_display_name || model.provider_model_name }}</p>
                    <p class="text-xs text-muted-foreground truncate font-mono">{{ model.provider_model_name }}</p>
                  </div>
                  <Badge
                    :variant="model.is_active ? 'outline' : 'secondary'"
                    :class="model.is_active ? 'text-green-600 border-green-500/60' : ''"
                    class="text-xs shrink-0"
                  >
                    {{ model.is_active ? '活跃' : '停用' }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <Button
        variant="outline"
        @click="$emit('update:open', false)"
      >
        关闭
      </Button>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Layers, Loader2, ChevronRight, ChevronLeft } from 'lucide-vue-next'
import Dialog from '@/components/ui/dialog/Dialog.vue'
import Button from '@/components/ui/button.vue'
import Badge from '@/components/ui/badge.vue'
import Checkbox from '@/components/ui/checkbox.vue'
import { useToast } from '@/composables/useToast'
import { parseApiError } from '@/utils/errorParser'
import {
  getGlobalModels,
  type GlobalModelResponse
} from '@/api/endpoints/global-models'
import {
  getProviderModels,
  batchAssignModelsToProvider,
  deleteModel,
  type Model
} from '@/api/endpoints'

const props = defineProps<{
  open: boolean
  providerId: string
  providerName: string
  providerIdentifier: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'changed': []
}>()

const { error: showError, success } = useToast()

// 状态
const loadingGlobalModels = ref(false)
const submittingAdd = ref(false)
const submittingRemove = ref(false)

// 数据
const allGlobalModels = ref<GlobalModelResponse[]>([])
const existingModels = ref<Model[]>([])

// 选择状态
const selectedLeftIds = ref<string[]>([])
const selectedRightIds = ref<string[]>([])

// 计算可添加的模型（排除已关联的）
const availableModels = computed(() => {
  const existingGlobalModelIds = new Set(
    existingModels.value
      .filter(m => m.global_model_id)
      .map(m => m.global_model_id)
  )
  return allGlobalModels.value.filter(m => !existingGlobalModelIds.has(m.id))
})

// 全选状态
const isAllLeftSelected = computed(() =>
  availableModels.value.length > 0 &&
  selectedLeftIds.value.length === availableModels.value.length
)

const isAllRightSelected = computed(() =>
  existingModels.value.length > 0 &&
  selectedRightIds.value.length === existingModels.value.length
)

// 监听打开状态
watch(() => props.open, async (isOpen) => {
  if (isOpen && props.providerId) {
    await loadData()
  } else {
    // 重置状态
    selectedLeftIds.value = []
    selectedRightIds.value = []
  }
})

// 加载数据
async function loadData() {
  await Promise.all([loadGlobalModels(), loadExistingModels()])
}

// 加载全局模型列表
async function loadGlobalModels() {
  try {
    loadingGlobalModels.value = true
    const response = await getGlobalModels({ limit: 1000 })
    allGlobalModels.value = response.models
  } catch (err: any) {
    showError(parseApiError(err, '加载全局模型失败'), '错误')
  } finally {
    loadingGlobalModels.value = false
  }
}

// 加载已关联的模型
async function loadExistingModels() {
  try {
    existingModels.value = await getProviderModels(props.providerId)
  } catch (err: any) {
    showError(parseApiError(err, '加载已关联模型失败'), '错误')
  }
}

// 切换左侧选择
function toggleLeftSelection(id: string) {
  const index = selectedLeftIds.value.indexOf(id)
  if (index === -1) {
    selectedLeftIds.value.push(id)
  } else {
    selectedLeftIds.value.splice(index, 1)
  }
}

// 切换右侧选择
function toggleRightSelection(id: string) {
  const index = selectedRightIds.value.indexOf(id)
  if (index === -1) {
    selectedRightIds.value.push(id)
  } else {
    selectedRightIds.value.splice(index, 1)
  }
}

// 全选/取消全选左侧
function toggleSelectAllLeft() {
  if (isAllLeftSelected.value) {
    selectedLeftIds.value = []
  } else {
    selectedLeftIds.value = availableModels.value.map(m => m.id)
  }
}

// 全选/取消全选右侧
function toggleSelectAllRight() {
  if (isAllRightSelected.value) {
    selectedRightIds.value = []
  } else {
    selectedRightIds.value = existingModels.value.map(m => m.id)
  }
}

// 批量添加选中的模型
async function batchAddSelected() {
  if (selectedLeftIds.value.length === 0) return

  try {
    submittingAdd.value = true
    const result = await batchAssignModelsToProvider(props.providerId, selectedLeftIds.value)

    if (result.success.length > 0) {
      success(`成功添加 ${result.success.length} 个模型`)
    }

    if (result.errors.length > 0) {
      const errorMessages = result.errors.map(e => e.error).join(', ')
      showError(`部分模型添加失败: ${errorMessages}`, '警告')
    }

    selectedLeftIds.value = []
    await loadExistingModels()
    emit('changed')
  } catch (err: any) {
    showError(parseApiError(err, '批量添加失败'), '错误')
  } finally {
    submittingAdd.value = false
  }
}

// 批量移除选中的模型
async function batchRemoveSelected() {
  if (selectedRightIds.value.length === 0) return

  try {
    submittingRemove.value = true
    let successCount = 0
    const errors: string[] = []

    for (const modelId of selectedRightIds.value) {
      try {
        await deleteModel(props.providerId, modelId)
        successCount++
      } catch (err: any) {
        errors.push(parseApiError(err, '删除失败'))
      }
    }

    if (successCount > 0) {
      success(`成功移除 ${successCount} 个模型`)
    }

    if (errors.length > 0) {
      showError(`部分模型移除失败: ${errors.join(', ')}`, '警告')
    }

    selectedRightIds.value = []
    await loadExistingModels()
    emit('changed')
  } catch (err: any) {
    showError(parseApiError(err, '批量移除失败'), '错误')
  } finally {
    submittingRemove.value = false
  }
}
</script>
