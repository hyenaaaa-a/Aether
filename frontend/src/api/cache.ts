/**
 * 缓存监控 API 客户端
 */

import api from './client'

export interface CacheStats {
  scheduler: string
  cache_reservation_ratio: number
  affinity_stats: {
    storage_type: string
    total_affinities: number
    active_affinities: number | string
    cache_hits: number
    cache_misses: number
    cache_hit_rate: number
    cache_invalidations: number
    provider_switches: number
    key_switches: number
    config: {
      default_ttl: number
    }
  }
}

export interface DynamicReservationConfig {
  probe_phase_requests: number
  probe_reservation: number
  stable_min_reservation: number
  stable_max_reservation: number
  low_load_threshold: number
  high_load_threshold: number
  success_count_for_full_confidence: number
  cooldown_hours_for_full_confidence: number
}

export interface CacheConfig {
  cache_ttl_seconds: number
  cache_reservation_ratio: number
  dynamic_reservation?: {
    enabled: boolean
    config: DynamicReservationConfig
    description: Record<string, string>
  }
  description: {
    cache_ttl: string
    cache_reservation_ratio: string
    dynamic_reservation?: string
  }
}

export interface UserAffinity {
  affinity_key: string
  user_api_key_name: string | null
  user_api_key_prefix: string | null  // 用户 API Key 脱敏显示（前4...后4）
  is_standalone: boolean
  user_id: string | null
  username: string | null
  email: string | null
  provider_id: string
  provider_name: string | null
  endpoint_id: string
  endpoint_api_format: string | null
  endpoint_url: string | null
  key_id: string
  key_name: string | null
  key_prefix: string | null  // Provider Key 脱敏显示（前4...后4）
  rate_multiplier: number
  model_name: string | null  // 模型名称（如 claude-haiku-4-5-20250514）
  model_display_name: string | null  // 模型显示名称（如 Claude Haiku 4.5）
  api_format: string | null  // API 格式 (claude/openai)
  created_at: number
  expire_at: number
  request_count: number
}

export interface AffinityListResponse {
  items: UserAffinity[]
  total: number
  matched_user_id?: string | null
}

export const cacheApi = {
  /**
   * 获取缓存统计信息
   */
  async getStats(): Promise<CacheStats> {
    const response = await api.get('/api/admin/monitoring/cache/stats')
    return response.data.data
  },

  /**
   * 获取缓存配置
   */
  async getConfig(): Promise<CacheConfig> {
    const response = await api.get('/api/admin/monitoring/cache/config')
    return response.data.data
  },

  /**
   * 查询用户缓存亲和性（现在返回该用户所有端点的亲和性列表）
   *
   * @param userIdentifier 用户标识符，支持：用户名、邮箱、User UUID、API Key ID
   */
  async getUserAffinity(userIdentifier: string): Promise<UserAffinity[] | null> {
    const response = await api.get(`/api/admin/monitoring/cache/affinity/${userIdentifier}`)
    if (response.data.status === 'not_found') {
      return null
    }
    return response.data.affinities
  },

  /**
   * 清除用户缓存
   *
   * @param userIdentifier 用户标识符，支持：用户名、邮箱、User UUID、API Key ID
   */
  async clearUserCache(userIdentifier: string): Promise<void> {
    await api.delete(`/api/admin/monitoring/cache/users/${userIdentifier}`)
  },

  /**
   * 清除所有缓存
   */
  async clearAllCache(): Promise<{ count: number }> {
    const response = await api.delete('/api/admin/monitoring/cache')
    return response.data
  },

  /**
   * 清除指定Provider的所有缓存
   */
  async clearProviderCache(providerId: string): Promise<{ count: number; provider_id: string }> {
    const response = await api.delete(`/api/admin/monitoring/cache/providers/${providerId}`)
    return response.data
  },

  /**
   * 获取缓存亲和性列表
   */
  async listAffinities(keyword?: string): Promise<AffinityListResponse> {
    const response = await api.get('/api/admin/monitoring/cache/affinities', {
      params: keyword ? { keyword } : undefined
    })
    return response.data.data
  }
}

// 导出便捷函数
export const {
  getStats,
  getConfig,
  getUserAffinity,
  clearUserCache,
  clearAllCache,
  clearProviderCache,
  listAffinities
} = cacheApi
