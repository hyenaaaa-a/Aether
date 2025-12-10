/**
 * 从后端响应中提取错误消息
 * 后端统一返回格式: {"error": {"type": "...", "message": "..."}}
 */
export function extractErrorMessage(error: any, defaultMessage = '操作失败'): string {
  // 优先从响应中提取错误消息
  if (error.response?.data?.error?.message) {
    return error.response.data.error.message
  }

  // 如果是网络错误或其他异常
  if (error.message) {
    return error.message
  }

  // 返回默认消息
  return defaultMessage
}

/**
 * 错误类型枚举
 */
export const ErrorType = {
  NETWORK_ERROR: 'network_error',
  AUTH_ERROR: 'auth_error',
  VALIDATION_ERROR: 'validation_error',
  NOT_FOUND: 'not_found',
  PROVIDER_ERROR: 'provider_error',
  QUOTA_EXCEEDED: 'quota_exceeded',
  RATE_LIMIT: 'rate_limit',
  MODEL_NOT_SUPPORTED: 'model_not_supported',
  INTERNAL_ERROR: 'internal_error',
  HTTP_ERROR: 'http_error'
} as const

export type ErrorType = typeof ErrorType[keyof typeof ErrorType]

/**
 * 从后端响应中提取错误类型
 */
export function extractErrorType(error: any): ErrorType | null {
  if (error.response?.data?.error?.type) {
    return error.response.data.error.type as ErrorType
  }
  return null
}

/**
 * 检查是否为特定类型的错误
 */
export function isErrorType(error: any, type: ErrorType): boolean {
  return extractErrorType(error) === type
}