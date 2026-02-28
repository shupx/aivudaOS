<script setup>
import { robotState } from '../services/robotClient'
</script>

<template>
  <div class="content-grid">
    <article class="card">
      <h2>会话信息</h2>
      <p>用户：{{ robotState.me?.username }}</p>
      <p>角色：{{ robotState.me?.role }}</p>
    </article>
  </div>
</template>
