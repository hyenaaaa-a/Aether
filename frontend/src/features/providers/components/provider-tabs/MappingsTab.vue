<template>
  <Card class="overflow-hidden">
    <!-- 标题头部 -->
    <div class="p-4 border-b border-border/60">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-semibold leading-none">
            别名与映射管理
          </h3>
        </div>
        <Button
          v-if="!hideAddButton"
          @click="openCreateDialog"
          variant="outline"
          size="sm"
          class="h-8"
        >
          <Plus class="w-3.5 h-3.5 mr-1.5" />
          创建别名/映射
        </Button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>

    <!-- 别名列表 -->
    <div v-else-if="mappings.length > 0" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="text-left px-4 py-3 font-semibold">名称</th>
            <th class="text-left px-4 py-3 font-semibold w-24">类型</th>
            <th class="text-left px-4 py-3 font-semibold">指向模型</th>
            <th v-if="!hideAddButton" class="px-4 py-3 font-semibold w-28 text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="mapping in mappings"
            :key="mapping.id"
            class="border-b border-border/40 last:border-b-0 hover:bg-muted/30 transition-colors"
          >
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <!-- 状态指示灯 -->
                <span
                  class="w-2 h-2 rounded-full shrink-0"
                  :class="mapping.is_active ? 'bg-green-500' : 'bg-gray-300'"
                  :title="mapping.is_active ? '活跃' : '停用'"
                ></span>
                <span class="font-mono">{{ mapping.alias }}</span>
              </div>
            </td>
            <td class="px-4 py-3">
              <Badge variant="secondary" class="text-xs">
                {{ mapping.mapping_type === 'mapping' ? '映射' : '别名' }}
              </Badge>
            </td>
            <td class="px-4 py-3">
              {{ mapping.global_model_display_name || mapping.global_model_name }}
            </td>
            <td v-if="!hideAddButton" class="px-4 py-3">
              <div class="flex justify-center gap-1.5">
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8"
                  title="编辑"
                  @click="openEditDialog(mapping)"
                >
                  <Edit class="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8"
                  :disabled="togglingId === mapping.id"
                  @click="toggleActive(mapping)"
                  :title="mapping.is_active ? '点击停用' : '点击启用'"
                >
                  <Power class="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8 text-destructive hover:text-destructive"
                  title="删除"
                  @click="confirmDelete(mapping)"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 空状态 -->
    <div v-else class="p-8 text-center text-muted-foreground">
      <ArrowLeftRight class="w-12 h-12 mx-auto mb-3 opacity-50" />
      <p class="text-sm">暂无特定别名/映射</p>
      <p class="text-xs mt-1">点击上方按钮添加</p>
    </div>
  </Card>

  <!-- 使用共享的 AliasDialog 组件 -->
  <AliasDialog
    :open="dialogOpen"
    :editing-alias="editingAlias"
    :global-models="availableModels"
    :fixed-provider="fixedProviderOption"
    :show-provider-select="true"
    @update:open="handleDialogVisibility"
    @submit="handleAliasSubmit"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeftRight, Plus, Edit, Trash2, Power } from 'lucide-vue-next'
import Card from '@/components/ui/card.vue'
import Badge from '@/components/ui/badge.vue'
import Button from '@/components/ui/button.vue'
import AliasDialog from '@/features/models/components/AliasDialog.vue'
import { useToast } from '@/composables/useToast'
import {
  getAliases,
  createAlias,
  updateAlias,
  deleteAlias,
  type ModelAlias,
  type CreateModelAliasRequest,
  type UpdateModelAliasRequest,
} from '@/api/endpoints/aliases'
import { listGlobalModels, type GlobalModelResponse } from '@/api/global-models'

const props = withDefaults(defineProps<{
  provider: any
  hideAddButton?: boolean
}>(), {
  hideAddButton: false
})

const emit = defineEmits<{
  refresh: []
}>()

const { success, error: showError } = useToast()

// 状态
const loading = ref(false)
const submitting = ref(false)
const togglingId = ref<string | null>(null)
const mappings = ref<ModelAlias[]>([])
const availableModels = ref<GlobalModelResponse[]>([])
const dialogOpen = ref(false)
const editingAlias = ref<ModelAlias | null>(null)

// 固定的 Provider 选项（传递给 AliasDialog）
const fixedProviderOption = computed(() => ({
  id: props.provider.id,
  name: props.provider.name,
  display_name: props.provider.display_name
}))

// 加载映射 (实际返回的是该 Provider 的别名列表)
async function loadMappings() {
  try {
    loading.value = true
    mappings.value = await getAliases({ provider_id: props.provider.id })
  } catch (err: any) {
    showError(err.response?.data?.detail || '加载失败', '错误')
  } finally {
    loading.value = false
  }
}

// 加载可用的 GlobalModel 列表
async function loadAvailableModels() {
  try {
    const response = await listGlobalModels({ limit: 1000, is_active: true })
    availableModels.value = response.models || []
  } catch (err: any) {
    showError(err.response?.data?.detail || '加载模型列表失败', '错误')
  }
}

// 打开创建对话框
function openCreateDialog() {
  editingAlias.value = null
  dialogOpen.value = true
}

// 打开编辑对话框
function openEditDialog(alias: ModelAlias) {
  editingAlias.value = alias
  dialogOpen.value = true
}

// 处理对话框可见性变化
function handleDialogVisibility(value: boolean) {
  dialogOpen.value = value
  if (!value) {
    editingAlias.value = null
  }
}

// 处理别名提交（来自 AliasDialog 组件）
async function handleAliasSubmit(data: CreateModelAliasRequest | UpdateModelAliasRequest, isEdit: boolean) {
  submitting.value = true
  try {
    if (isEdit && editingAlias.value) {
      // 更新
      await updateAlias(editingAlias.value.id, data as UpdateModelAliasRequest)
      success(data.mapping_type === 'mapping' ? '映射已更新' : '别名已更新')
    } else {
      // 创建 - 确保 provider_id 设置为当前 Provider
      const createData = data as CreateModelAliasRequest
      createData.provider_id = props.provider.id
      await createAlias(createData)
      success(data.mapping_type === 'mapping' ? '映射已创建' : '别名已创建')
    }
    dialogOpen.value = false
    editingAlias.value = null
    await loadMappings()
    emit('refresh')
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message
    let errorMessage = detail
    if (detail === '映射已存在') {
      errorMessage = '该名称已存在，请使用其他名称'
    }
    showError(errorMessage, isEdit ? '更新失败' : '创建失败')
  } finally {
    submitting.value = false
  }
}

// 切换启用状态
async function toggleActive(alias: ModelAlias) {
  if (togglingId.value) return

  togglingId.value = alias.id
  try {
    const newStatus = !alias.is_active
    await updateAlias(alias.id, { is_active: newStatus })
    alias.is_active = newStatus
  } catch (err: any) {
    showError(err.response?.data?.detail || '操作失败', '错误')
  } finally {
    togglingId.value = null
  }
}

// 确认删除
async function confirmDelete(alias: ModelAlias) {
  const typeName = alias.mapping_type === 'mapping' ? '映射' : '别名'
  if (!confirm(`确定要删除${typeName} "${alias.alias}" 吗？`)) {
    return
  }

  try {
    await deleteAlias(alias.id)
    success(`${typeName}已删除`)
    await loadMappings()
    emit('refresh')
  } catch (err: any) {
    showError(err.response?.data?.detail || err.message, '删除失败')
  }
}

onMounted(() => {
  loadMappings()
  loadAvailableModels()
})
</script>
