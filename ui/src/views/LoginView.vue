<script setup>
import { useLogin } from '../composables/useLogin'

const { form, busy, error, submit } = useLogin()
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <h1>AivudaOS</h1>
      <p class="muted">登录系统控制台</p>

      <div class="field">
        <label>用户名</label>
        <input v-model.trim="form.username" placeholder="admin" @keyup.enter="submit" />
      </div>

      <div class="field">
        <label>密码</label>
        <input v-model="form.password" type="password" placeholder="admin123" @keyup.enter="submit" />
      </div>

      <button class="btn primary" :disabled="busy" @click="submit">
        {{ busy ? '登录中...' : '登录' }}
      </button>

      <p v-if="error" class="error-text">{{ error }}</p>
    </section>
  </main>
</template>
