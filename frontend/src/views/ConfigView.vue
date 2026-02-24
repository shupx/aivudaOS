<script setup>
import { droneState, saveConfig } from '../services/droneClient'
</script>

<template>
  <article class="card">
    <h2>配置管理</h2>
    <p class="tip">版本：{{ droneState.config?.version }}</p>
    <textarea v-model="droneState.configText" rows="14"></textarea>
    <div class="actions">
      <button class="btn" @click="saveConfig">保存配置</button>
    </div>
    <p class="ok" v-if="droneState.saveOk">{{ droneState.saveOk }}</p>
    <p class="error" v-if="droneState.saveError">{{ droneState.saveError }}</p>
  </article>
</template>
