import apiClient from './client'

// API密钥管理相关接口定义
export interface AdminApiKey {
  id: string // UUID
  user_id: string // UUID
  user_email?: string
  username?: string
  name?: string
  key_display?: string  // 脱敏后的密钥显示
  is_active: boolean
  is_standalone: boolean  // 是否为独立余额Key
  balance_used_usd?: number  // 已使用余额（仅独立Key）
  current_balance_usd?: number | null  // 当前余额（独立Key预付费模式，null表示无限制）
  total_requests?: number
  total_tokens?: number
  total_cost_usd?: number
  rate_limit?: number
  allowed_providers?: string[] | null  // 允许的提供商列表
  allowed_api_formats?: string[] | null  // 允许的 API 格式列表
  allowed_models?: string[] | null  // 允许的模型列表
  auto_delete_on_expiry?: boolean  // 过期后是否自动删除
  last_used_at?: string
  expires_at?: string
  created_at: string
  updated_at?: string
}

export interface CreateStandaloneApiKeyRequest {
  name?: string
  allowed_providers?: string[] | null
  allowed_api_formats?: string[] | null
  allowed_models?: string[] | null
  rate_limit?: number
  expire_days?: number | null  // null = 永不过期
  initial_balance_usd: number  // 初始余额，必须设置
  auto_delete_on_expiry?: boolean  // 过期后是否自动删除
}

export interface AdminApiKeysResponse {
  api_keys: AdminApiKey[]
  total: number
  limit: number
  skip: number
}

export interface ApiKeyToggleResponse {
  id: string // UUID
  is_active: boolean
  message: string
}

// 管理员API密钥管理相关API
export const adminApi = {
  // 获取所有独立余额Keys列表
  async getAllApiKeys(params?: {
    skip?: number
    limit?: number
    is_active?: boolean
  }): Promise<AdminApiKeysResponse> {
    const response = await apiClient.get<AdminApiKeysResponse>('/api/admin/api-keys', {
      params: params
    })
    return response.data
  },

  // 创建独立余额Key
  async createStandaloneApiKey(data: CreateStandaloneApiKeyRequest): Promise<AdminApiKey & { key: string }> {
    const response = await apiClient.post<AdminApiKey & { key: string }>(
      '/api/admin/api-keys',
      data
    )
    return response.data
  },

  // 更新独立余额Key
  async updateApiKey(keyId: string, data: Partial<CreateStandaloneApiKeyRequest>): Promise<AdminApiKey & { message: string }> {
    const response = await apiClient.put<AdminApiKey & { message: string }>(
      `/api/admin/api-keys/${keyId}`,
      data
    )
    return response.data
  },

  // 切换API密钥状态（启用/禁用）
  async toggleApiKey(keyId: string): Promise<ApiKeyToggleResponse> {
    const response = await apiClient.patch<ApiKeyToggleResponse>(
      `/api/admin/api-keys/${keyId}`
    )
    return response.data
  },

  // 删除API密钥
  async deleteApiKey(keyId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string}>(
      `/api/admin/api-keys/${keyId}`
    )
    return response.data
  },

  // 为独立余额Key调整余额
  async addApiKeyBalance(keyId: string, amountUsd: number): Promise<AdminApiKey & { message: string }> {
    const response = await apiClient.patch<AdminApiKey & { message: string }>(
      `/api/admin/api-keys/${keyId}/balance`,
      { amount_usd: amountUsd }
    )
    return response.data
  },

  // 获取API密钥详情（可选包含完整密钥）
  async getApiKeyDetail(keyId: string, includeKey: boolean = false): Promise<AdminApiKey & { key?: string }> {
    const response = await apiClient.get<AdminApiKey & { key?: string }>(
      `/api/admin/api-keys/${keyId}`,
      { params: { include_key: includeKey } }
    )
    return response.data
  },

  // 获取完整的API密钥（用于复制）- 便捷方法
  async getFullApiKey(keyId: string): Promise<{ key: string }> {
    const response = await apiClient.get<{ key: string }>(
      `/api/admin/api-keys/${keyId}`,
      { params: { include_key: true } }
    )
    return response.data
  },

  // 系统配置相关
  // 获取所有系统配置
  async getAllSystemConfigs(): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/system/configs')
    return response.data
  },

  // 获取特定系统配置
  async getSystemConfig(key: string): Promise<{ key: string; value: any }> {
    const response = await apiClient.get<{ key: string; value: any }>(
      `/api/admin/system/configs/${key}`
    )
    return response.data
  },

  // 更新系统配置
  async updateSystemConfig(
    key: string,
    value: any,
    description?: string
  ): Promise<{ key: string; value: any; description?: string }> {
    const response = await apiClient.put<{ key: string; value: any; description?: string }>(
      `/api/admin/system/configs/${key}`,
      { value, description }
    )
    return response.data
  },

  // 删除系统配置
  async deleteSystemConfig(key: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(
      `/api/admin/system/configs/${key}`
    )
    return response.data
  },

  // 获取系统统计
  async getSystemStats(): Promise<any> {
    const response = await apiClient.get<any>('/api/admin/system/stats')
    return response.data
  },

  // 获取可用的API格式列表
  async getApiFormats(): Promise<{ formats: Array<{ value: string; label: string; default_path: string; aliases: string[] }> }> {
    const response = await apiClient.get<{ formats: Array<{ value: string; label: string; default_path: string; aliases: string[] }> }>(
      '/api/admin/system/api-formats'
    )
    return response.data
  }
}
