<template>
  <div class="auth-page">
    <div class="auth-bg" aria-hidden="true">
      <div class="bg-orb orb-1" />
      <div class="bg-orb orb-2" />
    </div>

    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-logo">✂️</div>
        <h1 class="auth-title">{{ t('common.appName') }}</h1>
        <p class="auth-subtitle">{{ t('auth.loginTitle') }}</p>
      </div>

      <div class="auth-divider">
        <span>{{ t('auth.login') }}</span>
      </div>

      <form class="auth-form" @submit.prevent="handleLogin" novalidate>
        <div class="form-field">
          <label class="form-label" for="email">{{ t('auth.email') }}</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="input"
            :class="{ 'input-error': errors.email }"
            :placeholder="t('auth.emailPlaceholder')"
            autocomplete="email"
            autofocus
            @blur="validateEmail"
          />
          <span v-if="errors.email" class="field-error">{{ errors.email }}</span>
        </div>

        <div class="form-field">
          <label class="form-label" for="password">
            {{ t('auth.password') }}
          </label>
          <div class="input-wrap">
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="input input-with-suffix"
              :class="{ 'input-error': errors.password }"
              :placeholder="t('auth.passwordPlaceholder')"
              autocomplete="current-password"
              @blur="validatePassword"
            />
            <button type="button" class="input-suffix-btn" @click="showPassword = !showPassword" tabindex="-1">
              {{ showPassword ? t('auth.hide') : t('auth.show') }}
            </button>
          </div>
          <span v-if="errors.password" class="field-error">{{ errors.password }}</span>
        </div>

        <Transition name="slide-up">
          <div v-if="serverError" class="alert alert-error" role="alert">
            <span>⚠</span>
            <span>{{ serverError }}</span>
          </div>
        </Transition>

        <button type="submit" class="btn btn-primary btn-lg w-full" :disabled="loading">
          <span v-if="loading" class="btn-spinner" />
          {{ loading ? t('common.loading') : t('auth.login') }}
        </button>
      </form>

      <p class="auth-switch">
        {{ t('auth.noAccount') }}
        <RouterLink to="/register" class="auth-switch-link">{{ t('auth.goRegister') }} →</RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const serverError = ref('')
const errors = reactive({ email: '', password: '' })

function validateEmail() {
  if (!email.value) {
    errors.email = t('auth.emailRequired')
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
    errors.email = t('auth.emailInvalid')
  } else {
    errors.email = ''
  }
}

function validatePassword() {
  if (!password.value) {
    errors.password = t('auth.passwordRequired')
  } else {
    errors.password = ''
  }
}

async function handleLogin() {
  validateEmail()
  validatePassword()
  if (errors.email || errors.password) return

  serverError.value = ''
  loading.value = true
  try {
    await authStore.login(email.value, password.value)
    router.push('/dashboard')
  } catch (e: any) {
    const msg = e.response?.data?.detail
    if (typeof msg === 'string') {
      serverError.value = msg
    } else {
      serverError.value = t('auth.loginFailed')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* Layout */
.auth-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--space-6);
  overflow: hidden;
}

/* Background orbs */
.auth-bg { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.12;
}
.orb-1 {
  width: 600px; height: 600px;
  background: var(--color-primary);
  top: -200px; right: -100px;
  animation: float 8s ease-in-out infinite;
}
.orb-2 {
  width: 400px; height: 400px;
  background: #818cf8;
  bottom: -100px; left: -100px;
  animation: float 10s ease-in-out infinite reverse;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-30px); }
}

/* Card */
.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-10) var(--space-8);
  box-shadow: var(--shadow-lg);
}

/* Header */
.auth-header {
  text-align: center;
  margin-bottom: var(--space-6);
}
.auth-logo {
  font-size: 40px;
  margin-bottom: var(--space-3);
  filter: drop-shadow(0 0 12px rgba(99,102,241,0.4));
}
.auth-title {
  font-size: var(--text-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-2);
  background: linear-gradient(135deg, var(--color-text) 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.auth-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Divider with label */
.auth-divider {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}
.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-border);
}
.auth-divider span {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  font-weight: var(--weight-medium);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* Form */
.auth-form { display: flex; flex-direction: column; gap: var(--space-4); }

.form-field { display: flex; flex-direction: column; gap: var(--space-2); }

.form-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
}
.form-label-link {
  font-size: var(--text-xs);
  font-weight: var(--weight-normal);
  color: var(--color-text-muted);
}
.form-label-link:hover { color: var(--color-primary); }

.input-wrap { position: relative; }
.input-with-suffix { padding-right: 56px; }
.input-suffix-btn {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  transition: color var(--transition-fast);
}
.input-suffix-btn:hover { color: var(--color-text); }

.input-error {
  border-color: var(--color-error) !important;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15) !important;
}
.field-error {
  font-size: var(--text-xs);
  color: var(--color-error);
}

/* Spinner inside button */
.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Footer */
.auth-switch {
  text-align: center;
  margin-top: var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}
.auth-switch-link {
  color: var(--color-primary);
  font-weight: var(--weight-medium);
}
.auth-switch-link:hover { color: var(--color-primary-hover); }

/* Transitions */
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.2s ease; }
.slide-up-enter-from, .slide-up-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
