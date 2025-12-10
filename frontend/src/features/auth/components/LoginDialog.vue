<template>
  <Dialog v-model="isOpen" size="lg">
    <div class="space-y-6">
      <!-- Logo 和标题 -->
      <div class="flex flex-col items-center text-center">
        <div class="mb-4 rounded-3xl border border-primary/30 dark:border-[#cc785c]/30 bg-primary/5 dark:bg-transparent p-4 shadow-inner shadow-white/40 dark:shadow-[#cc785c]/10">
          <img src="/aether_adaptive.svg" alt="Logo" class="h-16 w-16" />
        </div>
        <h2 class="text-2xl font-semibold text-slate-900 dark:text-white">
          欢迎回来
        </h2>
      </div>

      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div class="space-y-2">
          <Label for="login-email">邮箱</Label>
          <Input
            id="login-email"
            v-model="form.email"
            type="email"
            required
            placeholder="hello@example.com"
            autocomplete="off"
          />
        </div>

        <div class="space-y-2">
          <Label for="login-password">密码</Label>
          <Input
            id="login-password"
            v-model="form.password"
            type="password"
            required
            placeholder="••••••••"
            autocomplete="off"
            @keyup.enter="handleLogin"
          />
        </div>

        <!-- 提示信息 -->
        <p class="text-xs text-slate-400 dark:text-muted-foreground/80">
          如需开通账户，请联系管理员配置访问权限
        </p>
      </form>
    </div>

    <template #footer>
      <Button
        @click="isOpen = false"
        type="button"
        variant="outline"
        class="w-full sm:w-auto border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400 hover:text-primary hover:border-primary/50 hover:bg-primary/5 dark:hover:text-primary dark:hover:border-primary/50 dark:hover:bg-primary/10"
      >
        取消
      </Button>
      <Button
        @click="handleLogin"
        :disabled="authStore.loading"
        class="w-full sm:w-auto bg-primary hover:bg-primary/90 text-white border-0"
      >
        {{ authStore.loading ? '登录中...' : '登录' }}
      </Button>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog } from '@/components/ui'
import Button from '@/components/ui/button.vue'
import Input from '@/components/ui/input.vue'
import Label from '@/components/ui/label.vue'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const router = useRouter()
const authStore = useAuthStore()
const { success: showSuccess, warning: showWarning, error: showError } = useToast()

const isOpen = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  isOpen.value = val
  // 打开对话框时重置表单
  if (val) {
    form.value = {
      email: '',
      password: ''
    }
  }
})

watch(isOpen, (val) => {
  emit('update:modelValue', val)
})

const form = ref({
  email: '',
  password: ''
})

async function handleLogin() {
  if (!form.value.email || !form.value.password) {
    showWarning('请输入邮箱和密码')
    return
  }

  const success = await authStore.login(form.value.email, form.value.password)
  if (success) {
    showSuccess('登录成功，正在跳转...')

    // 关闭对话框
    isOpen.value = false

    // 延迟一下让用户看到成功消息
    setTimeout(() => {
      // 根据用户角色跳转到不同的仪表盘
      const targetPath = authStore.user?.role === 'admin' ? '/admin/dashboard' : '/dashboard'
      router.push(targetPath)
    }, 1000)
  } else {
    showError(authStore.error || '登录失败，请检查邮箱和密码')
  }
}
</script>
