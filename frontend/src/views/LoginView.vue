<script setup>
import { login, droneState } from '../services/droneClient'
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
      <input v-model="droneState.username" />
    </div>
    <div class="form-row">
      <label>密码</label>
      <input v-model="droneState.password" type="password" @keyup.enter="submit" />
    </div>
    <button class="btn" :disabled="droneState.busy" @click="submit">登录</button>
    <p class="error" v-if="droneState.loginError">{{ droneState.loginError }}</p>
    <p class="tip">默认账号：admin / admin123</p>
  </section>
</template>
