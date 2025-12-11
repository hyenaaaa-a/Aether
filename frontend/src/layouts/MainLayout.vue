<template>
  <AppShell
    :show-notice="showAuthError"
    main-class=""
    :sidebar-class="sidebarClasses"
    :content-class="contentClasses"
  >
    <!-- GLOBAL TEXTURE (Paper Noise) -->
    <div class="absolute inset-0 pointer-events-none z-0 opacity-[0.03] mix-blend-multiply fixed"
         :style="{ backgroundImage: `url(\&quot;data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E\&quot;)` }">
    </div>

    <template #notice>
      <div class="flex w-full max-w-3xl items-center justify-between rounded-3xl bg-orange-500 px-6 py-3 text-white shadow-2xl ring-1 ring-white/30">
        <div class="flex items-center gap-3">
          <AlertTriangle class="h-5 w-5" />
          <span>认证已过期，请重新登录</span>
        </div>
        <Button
          @click="handleRelogin"
          variant="outline"
          size="sm"
          class="border-white/60 text-white hover:bg-white/10"
        >
          重新登录
        </Button>
      </div>
    </template>

    <template #sidebar>
      <!-- HEADER (Brand) -->
      <div class="shrink-0 flex items-center px-6 h-20">
         <RouterLink to="/" class="flex items-center gap-3 group transition-opacity hover:opacity-80">
            <HeaderLogo size="h-9 w-9" className="text-[#191919] dark:text-white" />
            <div class="flex flex-col justify-center">
                <h1 class="text-lg font-bold text-[#191919] dark:text-white leading-none">Aether</h1>
                <span class="text-[10px] text-[#91918d] dark:text-muted-foreground leading-none mt-1.5 font-medium tracking-wide">Multi Private Gateway</span>
            </div>
         </RouterLink>
      </div>

      <!-- NAVIGATION -->
      <div class="flex-1 overflow-y-auto py-2 scrollbar-none">
        <SidebarNav
          :items="navigation"
          :is-active="isNavActive"
        />
      </div>

      <!-- FOOTER (Profile) -->
      <div class="p-4 border-t border-[#3d3929]/5 dark:border-white/5">
        <div class="flex items-center justify-between p-2 rounded-xl">
           <div class="flex items-center gap-3 min-w-0">
              <div class="w-8 h-8 rounded-full bg-[#f0f0eb] dark:bg-white/10 border border-black/5 flex items-center justify-center text-xs font-bold text-[#3d3929] dark:text-[#d4a27f] shrink-0">
                {{ authStore.user?.username?.substring(0, 2).toUpperCase() }}
              </div>
              <div class="flex flex-col min-w-0">
                  <span class="text-xs font-semibold leading-none truncate opacity-90 text-foreground">{{ authStore.user?.username }}</span>
                  <span class="text-[10px] opacity-50 leading-none mt-1.5 text-muted-foreground">{{ authStore.user?.role === 'admin' ? '管理员' : '用户' }}</span>
              </div>
           </div>

           <div class="flex items-center gap-1">
              <RouterLink
                to="/dashboard/settings"
                class="p-1.5 hover:bg-muted/50 rounded-md text-muted-foreground hover:text-foreground transition-colors"
                title="个人设置"
              >
                  <Settings class="w-4 h-4" />
              </RouterLink>
              <button @click="handleLogout" class="p-1.5 rounded-md text-muted-foreground hover:text-red-500 transition-colors" title="退出登录">
                  <LogOut class="w-4 h-4" />
              </button>
           </div>
        </div>
      </div>
    </template>

    <template #header>
      <!-- Mobile Header -->
      <div class="lg:hidden p-4 flex items-center justify-between border-b border-border bg-background/80 backdrop-blur-md">
         <RouterLink to="/" class="flex items-center gap-2">
             <HeaderLogo size="h-8 w-8" className="text-[#191919] dark:text-white" />
             <span class="font-bold text-lg">Aether</span>
         </RouterLink>
         <MobileNav
            :items="navigation"
            :is-active="isNavActive"
            :active-path="route.path"
            :is-dark="isDark"
         />
      </div>

      <!-- Desktop Page Header -->
      <header class="hidden lg:flex h-16 px-8 items-center justify-between shrink-0 border-b border-[#3d3929]/5 dark:border-white/5 sticky top-0 z-40 backdrop-blur-md bg-[#faf9f5]/90 dark:bg-[#191714]/90">
          <div class="flex flex-col gap-0.5">
             <div class="flex items-center gap-2 text-sm text-muted-foreground">
                 <span>{{ currentSectionName }}</span>
                 <ChevronRight class="w-3 h-3 opacity-50" />
                 <span class="text-foreground font-medium">{{ currentPageName }}</span>
             </div>
          </div>

          <!-- Demo Mode Badge (center) -->
          <div v-if="isDemo" class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-xs font-medium">
            <AlertTriangle class="w-3.5 h-3.5" />
            <span>演示模式</span>
          </div>

          <div class="flex items-center gap-2">
               <!-- Theme Toggle -->
               <button
                 @click="toggleDarkMode"
                 class="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition"
                 :title="themeMode === 'system' ? '跟随系统' : themeMode === 'dark' ? '深色模式' : '浅色模式'"
               >
                   <SunMoon v-if="themeMode === 'system'" class="h-4 w-4" />
                   <SunMedium v-else-if="themeMode === 'light'" class="h-4 w-4" />
                   <Moon v-else class="h-4 w-4" />
               </button>
          </div>
      </header>
    </template>

    <RouterView />
  </AppShell>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDarkMode } from '@/composables/useDarkMode'
import { isDemoMode } from '@/config/demo'
import Button from '@/components/ui/button.vue'
import AppShell from '@/components/layout/AppShell.vue'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import MobileNav from '@/components/layout/MobileNav.vue'
import HeaderLogo from '@/components/HeaderLogo.vue'
import {
  Home,
  Users,
  Key,
  BarChart3,
  Cog,
  Settings,
  Activity,
  Shield,
  AlertTriangle,
  SunMedium,
  Moon,
  Gauge,
  Layers,
  FolderTree,
  Tag,
  Box,
  LogOut,
  SunMoon,
  ChevronRight,
  Megaphone,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { isDark, themeMode, toggleDarkMode } = useDarkMode()
const isDemo = computed(() => isDemoMode())

const showAuthError = ref(false)
let authCheckInterval: number | null = null

onMounted(() => {
  authCheckInterval = setInterval(() => {
    if (authStore.user && !authStore.token) {
      showAuthError.value = true
    }
  }, 5000)
})

onUnmounted(() => {
  if (authCheckInterval) {
    clearInterval(authCheckInterval)
    authCheckInterval = null
  }
})

function handleRelogin() {
  showAuthError.value = false
  router.push('/').then(() => {
    authStore.logout()
  })
}

function handleLogout() {
  authStore.logout()
  router.push('/')
}

function isNavActive(href: string) {
  if (href === '/dashboard' || href === '/admin/dashboard') {
    return route.path === href
  }
  return route.path === href || route.path.startsWith(`${href}/`)
}

// Navigation Data
const navigation = computed(() => {
  const baseNavigation = [
    {
      title: '概览',
      items: [
        { name: '仪表盘', href: '/dashboard', icon: Home },
        { name: '健康监控', href: '/dashboard/endpoint-status', icon: Activity },
      ]
    },
    {
      title: '资源',
      items: [
        { name: '模型目录', href: '/dashboard/models', icon: Box },
        { name: 'API 密钥', href: '/dashboard/api-keys', icon: Key },
      ]
    },
    {
      title: '账户',
      items: [
         { name: '使用统计', href: '/dashboard/usage', icon: BarChart3 },
      ]
    }
  ]

  const adminNavigation = [
     {
      title: '概览',
      items: [
        { name: '仪表盘', href: '/admin/dashboard', icon: Home },
        { name: '健康监控', href: '/admin/health-monitor', icon: Activity },
      ]
    },
    {
      title: '管理',
      items: [
        { name: '用户管理', href: '/admin/users', icon: Users },
        { name: '提供商', href: '/admin/providers', icon: FolderTree },
        { name: '模型管理', href: '/admin/models', icon: Layers },
        { name: '别名映射', href: '/admin/aliases', icon: Tag },
        { name: '独立密钥', href: '/admin/keys', icon: Key },
        { name: '使用记录', href: '/admin/usage', icon: BarChart3 },
      ]
    },
    {
      title: '系统',
      items: [
        { name: '公告管理', href: '/admin/announcements', icon: Megaphone },
        { name: '缓存监控', href: '/admin/cache-monitoring', icon: Gauge },
        { name: 'IP 安全', href: '/admin/ip-security', icon: Shield },
        { name: '审计日志', href: '/admin/audit-logs', icon: AlertTriangle },
        { name: '系统设置', href: '/admin/system', icon: Cog },
      ]
    }
  ]

  return authStore.user?.role === 'admin' ? adminNavigation : baseNavigation
})

// Dynamic Header Title
const currentSectionName = computed(() => {
    // Special case: personal settings page accessed by admin
    if (route.path === '/dashboard/settings') {
      return '账户'
    }
    // Find the group that contains the active item
    for (const group of navigation.value) {
      const hasActiveItem = group.items.some(item => isNavActive(item.href))
      if (hasActiveItem) {
        return group.title || ''
      }
    }
    return ''
})

const currentPageName = computed(() => {
    // Special case: personal settings page accessed by admin
    if (route.path === '/dashboard/settings') {
      return '个人设置'
    }
    // Flatten navigation to find matching item name
    const allItems = navigation.value.flatMap(group => group.items)
    const active = allItems.find(item => isNavActive(item.href))
    return active ? active.name : route.name?.toString() || '仪表盘'
})

// Styling Classes (Editorial)
const sidebarClasses = computed(() => {
    // Fixed width, border right, background match
    return `w-[260px] flex flex-col hidden lg:flex border-r border-[#3d3929]/5 dark:border-white/5 bg-[#faf9f5] dark:bg-[#1e1c19] h-screen sticky top-0`
})

const contentClasses = computed(() => {
    return `flex-1 min-w-0 bg-[#faf9f5] dark:bg-[#191714] text-[#3d3929] dark:text-[#d4a27f]`
})

</script>

<style scoped>
.scrollbar-none::-webkit-scrollbar { display: none; }
.scrollbar-none { -ms-overflow-style: none; scrollbar-width: none; }
</style>
