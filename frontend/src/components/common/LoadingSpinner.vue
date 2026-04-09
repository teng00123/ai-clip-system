<template>
  <div :class="['spinner-wrap', size]" :style="color ? { '--spin-color': color } : {}">
    <div class="spinner-ring" />
    <span v-if="label" class="spinner-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  size?: 'sm' | 'md' | 'lg'
  label?: string
  color?: string
}>()
</script>

<style scoped>
.spinner-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  --spin-color: var(--color-primary);
}

.spinner-ring {
  border: 2px solid var(--color-border);
  border-top-color: var(--spin-color);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.sm .spinner-ring  { width: 18px; height: 18px; border-width: 2px; }
.md .spinner-ring  { width: 32px; height: 32px; border-width: 3px; }
.lg .spinner-ring  { width: 48px; height: 48px; border-width: 3px; }

/* default = md */
.spinner-wrap:not(.sm):not(.lg) .spinner-ring { width: 32px; height: 32px; border-width: 3px; }

.spinner-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
