<template>
  <Dialog
    :model-value="open"
    @update:model-value="handleClose"
    :title="isEditing ? '编辑模型配置' : '添加模型'"
    :description="isEditing ? '修改模型价格和能力配置' : '为此 Provider 添加模型实现'"
    :icon="isEditing ? SquarePen : Layers"
    size="xl"
  >
    <form @submit.prevent="handleSubmit" class="space-y-4">
      <!-- 添加模式：选择全局模型 -->
      <div v-if="!isEditing" class="space-y-2">
        <Label for="global-model">选择模型 *</Label>
        <Select
          v-model:open="globalModelSelectOpen"
          :model-value="form.global_model_id"
          :disabled="loadingGlobalModels"
          @update:model-value="form.global_model_id = $event"
        >
          <SelectTrigger class="w-full">
            <SelectValue :placeholder="loadingGlobalModels ? '加载中...' : '请选择模型'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="model in availableGlobalModels"
              :key="model.id"
              :value="model.id"
            >
              {{ model.display_name }} ({{ model.name }})
            </SelectItem>
          </SelectContent>
        </Select>
        <p v-if="availableGlobalModels.length === 0 && !loadingGlobalModels" class="text-xs text-muted-foreground">
          所有全局模型已添加到此 Provider
        </p>
      </div>

      <!-- 编辑模式：显示模型信息 -->
      <div v-else class="rounded-lg border bg-muted/30 p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="font-semibold text-lg">{{ editingModel?.global_model_display_name || editingModel?.provider_model_name }}</p>
            <p class="text-sm text-muted-foreground font-mono">{{ editingModel?.provider_model_name }}</p>
          </div>
        </div>
      </div>

      <!-- 价格配置 -->
      <div class="space-y-4">
        <h4 class="font-semibold text-sm border-b pb-2">价格配置</h4>
        <TieredPricingEditor v-model="tieredPricing" :show-cache1h="showCache1h" />

        <!-- 按次计费 -->
        <div class="flex items-center gap-3 pt-2 border-t">
          <Label class="text-xs whitespace-nowrap">按次计费 ($/次)</Label>
          <Input
            :model-value="form.price_per_request ?? ''"
            type="number"
            step="0.001"
            min="0"
            class="w-32"
            placeholder="留空使用默认值"
            @update:model-value="(v) => form.price_per_request = parseNumberInput(v, { allowFloat: true })"
          />
          <span class="text-xs text-muted-foreground">每次请求固定费用，留空使用全局模型默认值</span>
        </div>
      </div>

      <!-- 能力配置 -->
      <div class="space-y-4">
        <h4 class="font-semibold text-sm border-b pb-2">能力配置</h4>

        <div class="grid grid-cols-2 gap-3">
          <label class="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-muted/50">
            <input
              type="checkbox"
              v-model="form.supports_streaming"
              :indeterminate="form.supports_streaming === undefined"
              class="rounded"
            />
            <Zap class="w-4 h-4 text-muted-foreground shrink-0" />
            <span class="text-sm font-medium">流式输出</span>
          </label>
          <label class="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-muted/50">
            <input
              type="checkbox"
              v-model="form.supports_image_generation"
              :indeterminate="form.supports_image_generation === undefined"
              class="rounded"
            />
            <Image class="w-4 h-4 text-muted-foreground shrink-0" />
            <span class="text-sm font-medium">图像生成</span>
          </label>
          <label class="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-muted/50">
            <input
              type="checkbox"
              v-model="form.supports_vision"
              :indeterminate="form.supports_vision === undefined"
              class="rounded"
            />
            <Eye class="w-4 h-4 text-muted-foreground shrink-0" />
            <span class="text-sm font-medium">视觉理解</span>
          </label>
          <label class="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-muted/50">
            <input
              type="checkbox"
              v-model="form.supports_function_calling"
              :indeterminate="form.supports_function_calling === undefined"
              class="rounded"
            />
            <Wrench class="w-4 h-4 text-muted-foreground shrink-0" />
            <span class="text-sm font-medium">工具调用</span>
          </label>
          <label class="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-muted/50">
            <input
              type="checkbox"
              v-model="form.supports_extended_thinking"
              :indeterminate="form.supports_extended_thinking === undefined"
              class="rounded"
            />
            <Brain class="w-4 h-4 text-muted-foreground shrink-0" />
            <span class="text-sm font-medium">深度思考</span>
          </label>
        </div>
      </div>

    </form>

    <template #footer>
      <Button variant="outline" @click="handleClose(false)">
        取消
      </Button>
      <Button @click="handleSubmit" :disabled="submitting || (!isEditing && !form.global_model_id)">
        <Loader2 v-if="submitting" class="w-4 h-4 mr-2 animate-spin" />
        {{ isEditing ? '保存' : '添加' }}
      </Button>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Eye, Wrench, Brain, Zap, Loader2, Image, Layers, SquarePen } from 'lucide-vue-next'
import { Dialog, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui'
import Button from '@/components/ui/button.vue'
import Input from '@/components/ui/input.vue'
import Label from '@/components/ui/label.vue'
import { useToast } from '@/composables/useToast'
import { parseNumberInput } from '@/utils/form'
import { createModel, updateModel, getProviderModels } from '@/api/endpoints/models'
import { listGlobalModels, type GlobalModelResponse } from '@/api/global-models'
import TieredPricingEditor from '@/features/models/components/TieredPricingEditor.vue'
import type { Model, TieredPricingConfig } from '@/api/endpoints'

interface Props {
  open: boolean
  providerId: string
  providerName?: string
  editingModel?: Model | null
}

const props = withDefaults(defineProps<Props>(), {
  providerName: '',
  editingModel: null
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  'saved': []
}>()

const { error: showError, success: showSuccess } = useToast()

const isEditing = computed(() => !!props.editingModel)

// 计算是否显示 1h 缓存输入框
const showCache1h = computed(() => {
  if (isEditing.value) {
    // 编辑模式：检查当前配置是否有 1h 缓存配置（从 tiered_pricing 或 effective_tiered_pricing 中检测）
    const pricing = props.editingModel?.tiered_pricing || props.editingModel?.effective_tiered_pricing
    return pricing?.tiers?.some(t => t.cache_ttl_pricing?.some(c => c.ttl_minutes === 60)) ?? false
  } else {
    // 添加模式：从选中的全局模型中读取 supported_capabilities
    const selectedModel = availableGlobalModels.value.find(m => m.id === form.value.global_model_id)
    return selectedModel?.supported_capabilities?.includes('cache_1h') ?? false
  }
})

// 表单状态
const submitting = ref(false)
const loadingGlobalModels = ref(false)
const availableGlobalModels = ref<GlobalModelResponse[]>([])
const globalModelSelectOpen = ref(false)

// 阶梯计费配置
const tieredPricing = ref<TieredPricingConfig | null>(null)
// 跟踪用户是否修改了阶梯配置（用于判断是否提交）
const tieredPricingModified = ref(false)
// 保存原始配置用于比较
const originalTieredPricing = ref<string>('')

const form = ref({
  global_model_id: '',
  price_per_request: undefined as number | undefined,
  // 能力配置
  supports_vision: undefined as boolean | undefined,
  supports_function_calling: undefined as boolean | undefined,
  supports_streaming: undefined as boolean | undefined,
  supports_extended_thinking: undefined as boolean | undefined,
  supports_image_generation: undefined as boolean | undefined,
  is_active: true
})

// 监听 open 变化
watch(() => props.open, async (newOpen) => {
  if (newOpen) {
    resetForm()
    if (props.editingModel) {
      // 编辑模式：填充表单
      form.value = {
        global_model_id: props.editingModel.global_model_id || '',
        price_per_request: props.editingModel.price_per_request ?? undefined,
        supports_vision: props.editingModel.supports_vision ?? undefined,
        supports_function_calling: props.editingModel.supports_function_calling ?? undefined,
        supports_streaming: props.editingModel.supports_streaming ?? undefined,
        supports_extended_thinking: props.editingModel.supports_extended_thinking ?? undefined,
        supports_image_generation: props.editingModel.supports_image_generation ?? undefined,
        is_active: props.editingModel.is_active
      }
      // 加载阶梯计费配置：优先使用 Provider 自定义配置，否则使用有效配置（继承自全局模型）
      const pricing = props.editingModel.tiered_pricing || props.editingModel.effective_tiered_pricing
      if (pricing) {
        tieredPricing.value = JSON.parse(JSON.stringify(pricing))
      }
    } else {
      // 添加模式：加载可用全局模型
      await loadAvailableGlobalModels()
    }
  }
})

// 添加模式：选择全局模型时显示其阶梯计费配置（仅供预览）
// 注意：为保持继承关系，添加时只有用户修改了配置才提交 tiered_pricing
watch(() => form.value.global_model_id, (newId) => {
  if (!isEditing.value && newId) {
    const selectedModel = availableGlobalModels.value.find(m => m.id === newId)
    if (selectedModel?.default_tiered_pricing) {
      // 深拷贝阶梯计费配置用于预览
      const pricingCopy = JSON.parse(JSON.stringify(selectedModel.default_tiered_pricing))
      tieredPricing.value = pricingCopy
      // 保存原始配置用于比较
      originalTieredPricing.value = JSON.stringify(pricingCopy)
    } else {
      tieredPricing.value = null
      originalTieredPricing.value = ''
    }
    tieredPricingModified.value = false
    // 同时继承按次计费（仅供预览）
    form.value.price_per_request = selectedModel?.default_price_per_request ?? undefined
  }
})

// 监听阶梯配置变化，标记为已修改
watch(tieredPricing, (newValue) => {
  if (!isEditing.value && originalTieredPricing.value) {
    const newJson = JSON.stringify(newValue)
    tieredPricingModified.value = newJson !== originalTieredPricing.value
  }
}, { deep: true })

// 重置表单
function resetForm() {
  form.value = {
    global_model_id: '',
    price_per_request: undefined,
    supports_vision: undefined,
    supports_function_calling: undefined,
    supports_streaming: undefined,
    supports_extended_thinking: undefined,
    supports_image_generation: undefined,
    is_active: true
  }
  tieredPricing.value = null
  tieredPricingModified.value = false
  originalTieredPricing.value = ''
  availableGlobalModels.value = []
}

// 加载可用的全局模型（排除已添加的）
async function loadAvailableGlobalModels() {
  loadingGlobalModels.value = true
  try {
    const [globalModelsResponse, existingModels] = await Promise.all([
      listGlobalModels({ limit: 1000, is_active: true }),
      getProviderModels(props.providerId)
    ])
    const allGlobalModels = globalModelsResponse.models || []

    // 获取当前 provider 已添加的模型的 global_model_id 列表
    const existingGlobalModelIds = new Set(
      existingModels.map((m: Model) => m.global_model_id).filter(Boolean)
    )

    // 过滤掉已添加的模型
    availableGlobalModels.value = allGlobalModels.filter(
      (gm: GlobalModelResponse) => !existingGlobalModelIds.has(gm.id)
    )
  } catch (err: any) {
    showError(err.response?.data?.detail || '加载模型列表失败', '错误')
  } finally {
    loadingGlobalModels.value = false
  }
}

// 关闭对话框
function handleClose(value: boolean) {
  if (!submitting.value) {
    emit('update:open', value)
  }
}

// 提交表单
async function handleSubmit() {
  if (submitting.value) return

  submitting.value = true
  try {
    if (isEditing.value && props.editingModel) {
      // 编辑模式
      // 注意：使用 null 而不是 undefined 来显式清空字段（undefined 会被 JSON 序列化忽略）
      await updateModel(props.providerId, props.editingModel.id, {
        tiered_pricing: tieredPricing.value,
        price_per_request: form.value.price_per_request ?? null,
        supports_vision: form.value.supports_vision,
        supports_function_calling: form.value.supports_function_calling,
        supports_streaming: form.value.supports_streaming,
        supports_extended_thinking: form.value.supports_extended_thinking,
        supports_image_generation: form.value.supports_image_generation,
        is_active: form.value.is_active
      })
      showSuccess('模型配置已更新')
    } else {
      // 添加模式：只有用户修改了配置才提交 tiered_pricing，否则保持继承关系
      const selectedModel = availableGlobalModels.value.find(m => m.id === form.value.global_model_id)
      await createModel(props.providerId, {
        global_model_id: form.value.global_model_id,
        provider_model_name: selectedModel?.name || '',
        // 只有修改了才提交，否则传 undefined 让后端继承 GlobalModel 配置
        tiered_pricing: tieredPricingModified.value ? tieredPricing.value : undefined,
        price_per_request: form.value.price_per_request,
        supports_vision: form.value.supports_vision,
        supports_function_calling: form.value.supports_function_calling,
        supports_streaming: form.value.supports_streaming,
        supports_extended_thinking: form.value.supports_extended_thinking,
        supports_image_generation: form.value.supports_image_generation,
        is_active: form.value.is_active
      })
      showSuccess('模型已添加')
    }
    emit('update:open', false)
    emit('saved')
  } catch (err: any) {
    showError(err.response?.data?.detail || (isEditing.value ? '更新失败' : '添加失败'), '错误')
  } finally {
    submitting.value = false
  }
}
</script>
