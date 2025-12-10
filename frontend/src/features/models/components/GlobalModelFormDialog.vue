<template>
  <Dialog
    :model-value="open"
    :title="isEditMode ? '编辑模型' : '创建统一模型'"
    :description="isEditMode ? '修改模型配置和价格信息' : '添加一个新的全局模型定义'"
    :icon="isEditMode ? SquarePen : Layers"
    size="xl"
    @update:model-value="handleDialogUpdate"
  >
    <form @submit.prevent="handleSubmit" class="space-y-5 max-h-[70vh] overflow-y-auto pr-1">
      <!-- 基本信息 -->
      <section class="space-y-3">
        <h4 class="font-medium text-sm">基本信息</h4>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label for="model-name" class="text-xs">模型名称 *</Label>
            <Input
              id="model-name"
              v-model="form.name"
              placeholder="claude-3-5-sonnet-20241022"
              :disabled="isEditMode"
              required
            />
            <p v-if="!isEditMode" class="text-xs text-muted-foreground">创建后不可修改</p>
          </div>
          <div class="space-y-1.5">
            <Label for="model-display-name" class="text-xs">显示名称 *</Label>
            <Input
              id="model-display-name"
              v-model="form.display_name"
              placeholder="Claude 3.5 Sonnet"
              required
            />
          </div>
        </div>

        <div class="space-y-1.5">
          <Label for="model-description" class="text-xs">描述</Label>
          <Input
            id="model-description"
            v-model="form.description"
            placeholder="简短描述此模型的特点"
          />
        </div>
      </section>

      <!-- 能力配置 -->
      <section class="space-y-2">
        <h4 class="font-medium text-sm">默认能力</h4>
        <div class="flex flex-wrap gap-2">
          <label class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm">
            <input type="checkbox" v-model="form.default_supports_streaming" class="rounded" />
            <Zap class="w-3.5 h-3.5 text-muted-foreground" />
            <span>流式输出</span>
          </label>
          <label class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm">
            <input type="checkbox" v-model="form.default_supports_vision" class="rounded" />
            <Eye class="w-3.5 h-3.5 text-muted-foreground" />
            <span>视觉理解</span>
          </label>
          <label class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm">
            <input type="checkbox" v-model="form.default_supports_function_calling" class="rounded" />
            <Wrench class="w-3.5 h-3.5 text-muted-foreground" />
            <span>工具调用</span>
          </label>
          <label class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm">
            <input type="checkbox" v-model="form.default_supports_extended_thinking" class="rounded" />
            <Brain class="w-3.5 h-3.5 text-muted-foreground" />
            <span>深度思考</span>
          </label>
          <label class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm">
            <input type="checkbox" v-model="form.default_supports_image_generation" class="rounded" />
            <Image class="w-3.5 h-3.5 text-muted-foreground" />
            <span>图像生成</span>
          </label>
        </div>
      </section>

      <!-- Key 能力配置 -->
      <section v-if="availableCapabilities.length > 0" class="space-y-2">
        <h4 class="font-medium text-sm">Key 能力支持</h4>
        <div class="flex flex-wrap gap-2">
          <label
            v-for="cap in availableCapabilities"
            :key="cap.name"
            class="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-muted/30 cursor-pointer text-sm"
          >
            <input
              type="checkbox"
              :checked="form.supported_capabilities?.includes(cap.name)"
              @change="toggleCapability(cap.name)"
              class="rounded"
            />
            <span>{{ cap.display_name }}</span>
          </label>
        </div>
      </section>

      <!-- 价格配置 -->
      <section class="space-y-3">
        <h4 class="font-medium text-sm">价格配置</h4>
        <TieredPricingEditor v-model="tieredPricing" :show-cache1h="form.supported_capabilities?.includes('cache_1h')" />

        <!-- 按次计费 -->
        <div class="flex items-center gap-3 pt-2 border-t">
          <Label class="text-xs whitespace-nowrap">按次计费 ($/次)</Label>
          <Input
            :model-value="form.default_price_per_request ?? ''"
            type="number"
            step="0.001"
            min="0"
            class="w-32"
            placeholder="留空不启用"
            @update:model-value="(v) => form.default_price_per_request = parseNumberInput(v, { allowFloat: true })"
          />
          <span class="text-xs text-muted-foreground">每次请求固定费用，可与 Token 计费叠加</span>
        </div>
      </section>
    </form>

    <template #footer>
      <Button type="button" variant="outline" @click="handleCancel">
        取消
      </Button>
      <Button @click="handleSubmit" :disabled="submitting">
        <Loader2 v-if="submitting" class="w-4 h-4 mr-2 animate-spin" />
        {{ isEditMode ? '保存' : '创建' }}
      </Button>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Eye, Wrench, Brain, Zap, Image, Loader2, Layers, SquarePen } from 'lucide-vue-next'
import { Dialog, Button, Input, Label } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useFormDialog } from '@/composables/useFormDialog'
import { parseNumberInput } from '@/utils/form'
import TieredPricingEditor from './TieredPricingEditor.vue'
import {
  createGlobalModel,
  updateGlobalModel,
  type GlobalModelResponse,
  type GlobalModelCreate,
  type GlobalModelUpdate,
} from '@/api/global-models'
import type { TieredPricingConfig } from '@/api/endpoints/types'
import { getAllCapabilities, type CapabilityDefinition } from '@/api/endpoints'

const props = defineProps<{
  open: boolean
  model?: GlobalModelResponse | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'success': []
}>()

const { success, error: showError } = useToast()
const submitting = ref(false)

// 阶梯计费配置（统一使用，固定价格就是单阶梯）
const tieredPricing = ref<TieredPricingConfig | null>(null)

interface FormData {
  name: string
  display_name: string
  description?: string
  default_price_per_request?: number
  default_supports_streaming?: boolean
  default_supports_image_generation?: boolean
  default_supports_vision?: boolean
  default_supports_function_calling?: boolean
  default_supports_extended_thinking?: boolean
  supported_capabilities?: string[]
  is_active?: boolean
}

const defaultForm = (): FormData => ({
  name: '',
  display_name: '',
  description: '',
  default_price_per_request: undefined,
  default_supports_streaming: true,
  default_supports_image_generation: false,
  default_supports_vision: false,
  default_supports_function_calling: false,
  default_supports_extended_thinking: false,
  supported_capabilities: [],
  is_active: true,
})

const form = ref<FormData>(defaultForm())

// Key 能力选项
const availableCapabilities = ref<CapabilityDefinition[]>([])

// 加载可用能力列表
async function loadCapabilities() {
  try {
    availableCapabilities.value = await getAllCapabilities()
  } catch (err) {
    console.error('Failed to load capabilities:', err)
  }
}

// 切换能力
function toggleCapability(capName: string) {
  if (!form.value.supported_capabilities) {
    form.value.supported_capabilities = []
  }
  const index = form.value.supported_capabilities.indexOf(capName)
  if (index >= 0) {
    form.value.supported_capabilities.splice(index, 1)
  } else {
    form.value.supported_capabilities.push(capName)
  }
}

// 组件挂载时加载能力列表
onMounted(() => {
  loadCapabilities()
})

// 重置表单
function resetForm() {
  form.value = defaultForm()
  tieredPricing.value = null
}

// 加载模型数据（编辑模式）
function loadModelData() {
  if (!props.model) return
  form.value = {
    name: props.model.name,
    display_name: props.model.display_name,
    description: props.model.description,
    default_price_per_request: props.model.default_price_per_request,
    default_supports_streaming: props.model.default_supports_streaming,
    default_supports_image_generation: props.model.default_supports_image_generation,
    default_supports_vision: props.model.default_supports_vision,
    default_supports_function_calling: props.model.default_supports_function_calling,
    default_supports_extended_thinking: props.model.default_supports_extended_thinking,
    supported_capabilities: [...(props.model.supported_capabilities || [])],
    is_active: props.model.is_active,
  }

  // 加载阶梯计费配置（深拷贝）
  if (props.model.default_tiered_pricing) {
    tieredPricing.value = JSON.parse(JSON.stringify(props.model.default_tiered_pricing))
  }
}

// 使用 useFormDialog 统一处理对话框逻辑
const { isEditMode, handleDialogUpdate, handleCancel } = useFormDialog({
  isOpen: () => props.open,
  entity: () => props.model,
  isLoading: submitting,
  onClose: () => emit('update:open', false),
  loadData: loadModelData,
  resetForm,
})

async function handleSubmit() {
  if (!form.value.name || !form.value.display_name) {
    showError('请填写模型名称和显示名称')
    return
  }

  if (!tieredPricing.value?.tiers?.length) {
    showError('请配置至少一个价格阶梯')
    return
  }

  submitting.value = true
  try {
    if (isEditMode.value && props.model) {
      const updateData: GlobalModelUpdate = {
        display_name: form.value.display_name,
        description: form.value.description,
        // 使用 null 而不是 undefined 来显式清空字段
        default_price_per_request: form.value.default_price_per_request ?? null,
        default_tiered_pricing: tieredPricing.value,
        default_supports_streaming: form.value.default_supports_streaming,
        default_supports_image_generation: form.value.default_supports_image_generation,
        default_supports_vision: form.value.default_supports_vision,
        default_supports_function_calling: form.value.default_supports_function_calling,
        default_supports_extended_thinking: form.value.default_supports_extended_thinking,
        supported_capabilities: form.value.supported_capabilities?.length ? form.value.supported_capabilities : null,
        is_active: form.value.is_active,
      }
      await updateGlobalModel(props.model.id, updateData)
      success('模型更新成功')
    } else {
      const createData: GlobalModelCreate = {
        name: form.value.name!,
        display_name: form.value.display_name!,
        description: form.value.description,
        default_price_per_request: form.value.default_price_per_request || undefined,
        default_tiered_pricing: tieredPricing.value,
        default_supports_streaming: form.value.default_supports_streaming,
        default_supports_image_generation: form.value.default_supports_image_generation,
        default_supports_vision: form.value.default_supports_vision,
        default_supports_function_calling: form.value.default_supports_function_calling,
        default_supports_extended_thinking: form.value.default_supports_extended_thinking,
        supported_capabilities: form.value.supported_capabilities?.length ? form.value.supported_capabilities : undefined,
        is_active: form.value.is_active,
      }
      await createGlobalModel(createData)
      success('模型创建成功')
    }
    emit('update:open', false)
    emit('success')
  } catch (err: any) {
    showError(err.response?.data?.detail || err.message, isEditMode.value ? '更新失败' : '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>
