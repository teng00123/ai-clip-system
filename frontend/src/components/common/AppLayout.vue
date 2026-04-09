<template>
  <div class="app-layout">
    <NavBar />
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import NavBar from '@/components/common/NavBar.vue'
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}
</style>
