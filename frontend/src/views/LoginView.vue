<script setup>
import { login, robotState } from '../services/robotClient'
import { useRouter } from 'vue-router'

const router = useRouter()

async function submit() {
  const ok = await login()
  if (ok) {
    router.replace('/status')
  }
}
</script>

<template>
  <section class="card login-card">
    <h2>登录</h2>
    <div class="form-row">
      <label>用户名</label>
      <input v-model="robotState.username" />
    </div>
    <div class="form-row">
      <label>密码</label>
      <input v-model="robotState.password" type="password" @keyup.enter="submit" />
    </div>
    <button class="btn" :disabled="robotState.busy" @click="submit">登录</button>
    <p class="error" v-if="robotState.loginError">{{ robotState.loginError }}</p>
    <p class="tip">默认账号：admin / admin123</p>
  </section>
</template>
