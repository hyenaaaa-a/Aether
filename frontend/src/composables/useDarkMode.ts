import { effectScope, ref, watch, computed } from 'vue'

const THEME_STORAGE_KEY = 'theme'

// 主题模式类型
export type ThemeMode = 'system' | 'light' | 'dark'

// 全局共享的状态
const themeMode = ref<ThemeMode>('system')
const isDark = ref(false)
let initialized = false
let scope: ReturnType<typeof effectScope> | null = null
let mediaQuery: MediaQueryList | null = null

const applyDarkMode = (value: boolean) => {
  if (typeof document === 'undefined') {
    return
  }

  document.documentElement.classList.toggle('dark', value)

  if (document.body) {
    document.body.setAttribute('theme-mode', value ? 'dark' : 'light')
  }
}

const getSystemPreference = (): boolean => {
  if (typeof window === 'undefined') {
    return false
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const updateDarkMode = () => {
  if (themeMode.value === 'system') {
    isDark.value = getSystemPreference()
  } else {
    isDark.value = themeMode.value === 'dark'
  }
  applyDarkMode(isDark.value)
}

const handleSystemChange = (e: MediaQueryListEvent) => {
  if (themeMode.value === 'system') {
    isDark.value = e.matches
    applyDarkMode(isDark.value)
  }
}

const ensureWatcher = () => {
  if (scope) {
    return
  }

  scope = effectScope(true)
  scope.run(() => {
    watch(
      themeMode,
      (value) => {
        updateDarkMode()

        if (typeof window !== 'undefined') {
          localStorage.setItem(THEME_STORAGE_KEY, value)
        }
      },
      { flush: 'post' }
    )
  })
}

const initialize = () => {
  if (initialized) {
    return
  }

  initialized = true
  ensureWatcher()

  if (typeof window !== 'undefined') {
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null

    if (storedTheme === 'dark' || storedTheme === 'light' || storedTheme === 'system') {
      themeMode.value = storedTheme
    } else {
      // 兼容旧版本存储格式，旧版本直接存储 'dark' 或 'light'
      themeMode.value = 'system'
    }

    // 监听系统主题变化
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', handleSystemChange)
  }

  updateDarkMode()
}

export function useDarkMode() {
  initialize()
  ensureWatcher()
  applyDarkMode(isDark.value)

  const setDarkMode = (value: boolean) => {
    themeMode.value = value ? 'dark' : 'light'
  }

  const setThemeMode = (mode: ThemeMode) => {
    themeMode.value = mode
  }

  const toggleDarkMode = () => {
    // 循环切换：system -> light -> dark -> system
    if (themeMode.value === 'system') {
      themeMode.value = 'light'
    } else if (themeMode.value === 'light') {
      themeMode.value = 'dark'
    } else {
      themeMode.value = 'system'
    }
  }

  // 是否为跟随系统模式
  const isSystemMode = computed(() => themeMode.value === 'system')

  return {
    isDark,
    themeMode,
    isSystemMode,
    toggleDarkMode,
    setDarkMode,
    setThemeMode
  }
}
