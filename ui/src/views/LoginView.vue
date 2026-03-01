<script setup>
import { useI18n } from 'vue-i18n'
import { useLogin } from '../composables/useLogin'

const { t } = useI18n()
const { form, busy, error, submit } = useLogin()
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <h1>AivudaOS</h1>
      <p class="muted">{{ t('login.subtitle') }}</p>

      <div class="field">
        <label>{{ t('login.username') }}</label>
        <input v-model.trim="form.username" placeholder="admin" @keyup.enter="submit" />
      </div>

      <div class="field">
        <label>{{ t('login.password') }}</label>
        <input v-model="form.password" type="password" placeholder="admin123" @keyup.enter="submit" />
      </div>

      <button class="btn primary" :disabled="busy" @click="submit">
        {{ busy ? t('login.loggingIn') : t('login.login') }}
      </button>

      <p v-if="error" class="error-text">{{ error }}</p>
    </section>
  </main>
</template>
