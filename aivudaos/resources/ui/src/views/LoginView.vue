<script setup>
import { useI18n } from 'vue-i18n'
import { useLogin } from '../composables/useLogin'
import { NCard, NForm, NFormItem, NInput, NButton, NSpace, NText, NAlert } from 'naive-ui'

const { t } = useI18n()
const { form, busy, error, submit } = useLogin()
</script>

<template>
  <main style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background-color: #f4f7f9; padding: 20px;">
    <NCard style="width: 100%; max-width: 420px;">
      <div style="text-align: center; margin-bottom: 24px;">
        <NText style="font-size: 28px; font-weight: 700;">AivudaOS</NText>
        <div style="margin-top: 8px;">
           <NText depth="3">{{ t('login.subtitle') }}</NText>
        </div>
      </div>

      <NForm @submit.prevent="submit" size="large">
        <NFormItem :label="t('login.username')">
          <NInput v-model:value="form.username" placeholder="admin" @keyup.enter="submit" />
        </NFormItem>

        <NFormItem :label="t('login.password')">
          <NInput v-model:value="form.password" type="password" show-password-on="click" placeholder="admin123" @keyup.enter="submit" />
        </NFormItem>

        <NButton type="primary" block :loading="busy" @click="submit" size="large" style="margin-top: 12px;">
          {{ t('login.login') }}
        </NButton>

        <NAlert v-if="error" type="error" style="margin-top: 16px;">
          {{ error }}
        </NAlert>
      </NForm>
    </NCard>
  </main>
</template>
