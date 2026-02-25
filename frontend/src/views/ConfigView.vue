<script setup>
import { robotState, saveConfig } from '../services/robotClient'
</script>

<template>
  <article class="card">
    <h2>配置管理</h2>
    <p class="tip">版本：{{ robotState.config?.version }}</p>
    <textarea v-model="robotState.configText" rows="14"></textarea>
    <div class="actions">
      <button class="btn" @click="saveConfig">保存配置</button>
    </div>
    <p class="ok" v-if="robotState.saveOk">{{ robotState.saveOk }}</p>
    <p class="error" v-if="robotState.saveError">{{ robotState.saveError }}</p>
  </article>
</template>
