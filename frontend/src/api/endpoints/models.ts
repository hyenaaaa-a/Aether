import client from '../client'
import type {
  Model,
  ModelCreate,
  ModelUpdate,
  ModelCatalogResponse,
  ProviderAvailableSourceModelsResponse,
  UpdateModelMappingRequest,
  UpdateModelMappingResponse,
  DeleteModelMappingResponse
} from './types'

/**
 * 获取 Provider 的所有模型
 */
export async function getProviderModels(
  providerId: string,
  params?: {
    is_active?: boolean
    skip?: number
    limit?: number
  }
): Promise<Model[]> {
  const response = await client.get(`/api/admin/providers/${providerId}/models`, { params })
  return response.data
}

/**
 * 创建模型
 */
export async function createModel(
  providerId: string,
  data: ModelCreate
): Promise<Model> {
  const response = await client.post(`/api/admin/providers/${providerId}/models`, data)
  return response.data
}

/**
 * 获取模型详情
 */
export async function getModel(
  providerId: string,
  modelId: string
): Promise<Model> {
  const response = await client.get(`/api/admin/providers/${providerId}/models/${modelId}`)
  return response.data
}

/**
 * 更新模型
 */
export async function updateModel(
  providerId: string,
  modelId: string,
  data: ModelUpdate
): Promise<Model> {
  const response = await client.patch(`/api/admin/providers/${providerId}/models/${modelId}`, data)
  return response.data
}

/**
 * 删除模型
 */
export async function deleteModel(
  providerId: string,
  modelId: string
): Promise<{ message: string }> {
  const response = await client.delete(`/api/admin/providers/${providerId}/models/${modelId}`)
  return response.data
}

/**
 * 批量创建模型
 */
export async function batchCreateModels(
  providerId: string,
  modelsData: ModelCreate[]
): Promise<Model[]> {
  const response = await client.post(`/api/admin/providers/${providerId}/models/batch`, modelsData)
  return response.data
}

/**
 * 获取统一模型目录
 */
export async function getModelCatalog(): Promise<ModelCatalogResponse> {
  const response = await client.get('/api/admin/models/catalog')
  return response.data
}

/**
 * 获取 Provider 支持的统一模型列表
 */
export async function getProviderAvailableSourceModels(
  providerId: string
): Promise<ProviderAvailableSourceModelsResponse> {
  const response = await client.get(`/api/admin/providers/${providerId}/available-source-models`)
  return response.data
}

/**
 * 更新目录中的模型映射
 */
export async function updateCatalogMapping(
  mappingId: string,
  data: UpdateModelMappingRequest
): Promise<UpdateModelMappingResponse> {
  const response = await client.put(`/api/admin/models/catalog/mappings/${mappingId}`, data)
  return response.data
}

/**
 * 删除目录中的模型映射
 */
export async function deleteCatalogMapping(
  mappingId: string
): Promise<DeleteModelMappingResponse> {
  const response = await client.delete(`/api/admin/models/catalog/mappings/${mappingId}`)
  return response.data
}

/**
 * 批量为 Provider 关联 GlobalModels
 */
export async function batchAssignModelsToProvider(
  providerId: string,
  globalModelIds: string[]
): Promise<{
  success: Array<{
    global_model_id: string
    global_model_name: string
    model_id: string
  }>
  errors: Array<{
    global_model_id: string
    error: string
  }>
}> {
  const response = await client.post(
    `/api/admin/providers/${providerId}/assign-global-models`,
    { global_model_ids: globalModelIds }
  )
  return response.data
}

/**
 * 远程模型条目
 */
export interface RemoteModelItem {
  id: string
  object?: string
  created?: number
  owned_by?: string
}

/**
 * 获取远程模型响应
 */
export interface FetchRemoteModelsResponse {
  models: RemoteModelItem[]
  total: number
  endpoint_id: string
  endpoint_base_url: string
}

/**
 * 导入远程模型响应
 */
export interface ImportRemoteModelsResponse {
  success: Array<{
    model_id: string
    global_model_id: string
    global_model_name: string
    provider_model_id: string
    created_global_model: boolean
  }>
  errors: Array<{
    model_id: string
    error: string
  }>
}

/**
 * 从 Provider 远程 API 获取模型列表
 */
export async function fetchRemoteModels(
  providerId: string
): Promise<FetchRemoteModelsResponse> {
  const response = await client.get(
    `/api/admin/providers/${providerId}/fetch-remote-models`
  )
  return response.data
}

/**
 * 导入远程模型（自动创建 GlobalModel 和 Provider Model）
 */
export async function importRemoteModels(
  providerId: string,
  modelIds: string[]
): Promise<ImportRemoteModelsResponse> {
  const response = await client.post(
    `/api/admin/providers/${providerId}/import-remote-models`,
    { model_ids: modelIds }
  )
  return response.data
}

