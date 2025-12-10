/**
 * 模型别名管理 API
 */

import client from '../client'
import type { ModelMapping, ModelMappingCreate, ModelMappingUpdate } from './types'

export interface ModelAlias {
  id: string
  alias: string
  global_model_id: string
  global_model_name: string | null
  global_model_display_name: string | null
  provider_id: string | null
  provider_name: string | null
  scope: 'global' | 'provider'
  mapping_type: 'alias' | 'mapping'
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateModelAliasRequest {
  alias: string
  global_model_id: string
  provider_id?: string | null
  mapping_type?: 'alias' | 'mapping'
  is_active?: boolean
}

export interface UpdateModelAliasRequest {
  alias?: string
  global_model_id?: string
  provider_id?: string | null
  mapping_type?: 'alias' | 'mapping'
  is_active?: boolean
}

function transformMapping(mapping: ModelMapping): ModelAlias {
  return {
    id: mapping.id,
    alias: mapping.source_model,
    global_model_id: mapping.target_global_model_id,
    global_model_name: mapping.target_global_model_name,
    global_model_display_name: mapping.target_global_model_display_name,
    provider_id: mapping.provider_id ?? null,
    provider_name: mapping.provider_name ?? null,
    scope: mapping.scope,
    mapping_type: mapping.mapping_type || 'alias',
    is_active: mapping.is_active,
    created_at: mapping.created_at,
    updated_at: mapping.updated_at
  }
}

/**
 * 获取别名列表
 */
export async function getAliases(params?: {
  provider_id?: string
  global_model_id?: string
  is_active?: boolean
  skip?: number
  limit?: number
}): Promise<ModelAlias[]> {
  const response = await client.get('/api/admin/models/mappings', {
    params: {
      provider_id: params?.provider_id,
      target_global_model_id: params?.global_model_id,
      is_active: params?.is_active,
      skip: params?.skip,
      limit: params?.limit
    }
  })
  return (response.data as ModelMapping[]).map(transformMapping)
}

/**
 * 获取单个别名
 */
export async function getAlias(id: string): Promise<ModelAlias> {
  const response = await client.get(`/api/admin/models/mappings/${id}`)
  return transformMapping(response.data)
}

/**
 * 创建别名
 */
export async function createAlias(data: CreateModelAliasRequest): Promise<ModelAlias> {
  const payload: ModelMappingCreate = {
    source_model: data.alias,
    target_global_model_id: data.global_model_id,
    provider_id: data.provider_id ?? null,
    mapping_type: data.mapping_type ?? 'alias',
    is_active: data.is_active ?? true
  }
  const response = await client.post('/api/admin/models/mappings', payload)
  return transformMapping(response.data)
}

/**
 * 更新别名
 */
export async function updateAlias(id: string, data: UpdateModelAliasRequest): Promise<ModelAlias> {
  const payload: ModelMappingUpdate = {
    source_model: data.alias,
    target_global_model_id: data.global_model_id,
    provider_id: data.provider_id ?? null,
    mapping_type: data.mapping_type,
    is_active: data.is_active
  }
  const response = await client.patch(`/api/admin/models/mappings/${id}`, payload)
  return transformMapping(response.data)
}

/**
 * 删除别名
 */
export async function deleteAlias(id: string): Promise<void> {
  await client.delete(`/api/admin/models/mappings/${id}`)
}
