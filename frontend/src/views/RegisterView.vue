<template>
  <div class="auth-page">
    <div class="auth-bg" aria-hidden="true">
      <div class="bg-orb orb-1" />
      <div class="bg-orb orb-2" />
    </div>

    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-logo">✂️</div>
        <h1 class="auth-title">{{ t('auth.registerTitle') }}</h1>
        <p class="auth-subtitle">{{ t('auth.registerSubtitle') }}</p>
      </div>

      <div class="auth-divider"><span>{{ t('auth.fillInfo') }}</span></div>

      <form class="auth-form" @submit.prevent="handleRegister" novalidate>
        <!-- Email -->
        <div class="form-field">
          <label class="form-label" for="email">{{ t('auth.email') }} <span class="required">{{ t('auth.required') }}</span></label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="input"
            :class="{ 'input-error': errors.email }"
            placeholder="your@email.com"
            autocomplete="email"
            autofocus
            @blur="validateEmail"
          />
          <span v-if="errors.email" class="field-error">{{ errors.email }}</span>
        </div>

        <!-- Nickname -->
        <div class="form-field">
          <label class="form-label" for="nickname">
            {{ t('auth.nickname') }}
            <span class="form-label-hint">{{ t('auth.nicknameOptional') }}</span>
          </label>
          <input
            id="nickname"
            v-model="nickname"
            type="text"
            class="input"
            :placeholder="t('auth.nicknamePlaceholder')"
            autocomplete="nickname"
            maxlength="30"
          />
        </div>

        <!-- Password -->
        <div class="form-field">
          <label class="form-label" for="password">{{ t('auth.password') }} <span class="required">{{ t('auth.required') }}</span></label>
          <div class="input-wrap">
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="input input-with-suffix"
              :class="{ 'input-error': errors.password }"
              :placeholder="t('auth.passwordMin')"
              autocomplete="new-password"
              @blur="validatePassword"
              @input="updateStrength"
            />
            <button type="button" class="input-suffix-btn" @click="showPassword = !showPassword" tabindex="-1">
              {{ showPassword ? t('auth.hide') : t('auth.show') }}
            </button>
          </div>
          <span v-if="errors.password" class="field-error">{{ errors.password }}</span>

          <!-- Password strength indicator -->
          <div v-if="password" class="strength-bar">
            <div
              v-for="i in 4"
              :key="i"
              class="strength-segment"
              :class="{ active: i <= strength.level, [`level-${strength.level}`]: i <= strength.level }"
            />
            <span class="strength-label">{{ strength.label }}</span>
          </div>
        </div>

        <!-- Confirm password -->
        <div class="form-field">
          <label class="form-label" for="confirm">{{ t('auth.confirmPassword') }} <span class="required">{{ t('auth.required') }}</span></label>
          <input
            id="confirm"
            v-model="confirmPassword"
            :type="showPassword ? 'text' : 'password'"
            class="input"
            :class="{ 'input-error': errors.confirm }"
            :placeholder="t('auth.confirmPasswordPlaceholder')"
            autocomplete="new-password"
            @blur="validateConfirm"
          />
          <span v-if="errors.confirm" class="field-error">{{ errors.confirm }}</span>
        </div>

        <Transition name="slide-up">
          <div v-if="serverError" class="alert alert-error" role="alert">
            <span>⚠</span>
            <span>{{ serverError }}</span>
          </div>
        </Transition>

        <button type="submit" class="btn btn-primary btn-lg w-full" :disabled="loading">
          <span v-if="loading" class="btn-spinner" />
          {{ loading ? t('auth.registering') : t('auth.register') }}
        </button>

        <!-- Terms hint -->
        <p class="terms-hint">
          注册即表示你同意我们的
          <a href="#" @click.prevent>服务条款</a>
          和
          <a href="#" @click.prevent>隐私政策</a>
        </p>
      </form>

      <p class="auth-switch">
        {{ t('auth.hasAccount') }}
        <RouterLink to="/login" class="auth-switch-link">{{ t('auth.goLogin') }} →</RouterLink>
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
const nickname = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const loading = ref(false)
const serverError = ref('')
const errors = reactive({ email: '', password: '', confirm: '' })
const strength = reactive({ level: 0, label: '' })

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
  } else if (password.value.length < 8) {
    errors.password = t('auth.passwordMin')
  } else {
    errors.password = ''
  }
}

function validateConfirm() {
  if (!confirmPassword.value) {
    errors.confirm = t('auth.passwordRequired')
  } else if (confirmPassword.value !== password.value) {
    errors.confirm = t('auth.confirmPasswordMismatch')
  } else {
    errors.confirm = ''
  }
}

function updateStrength() {
  const p = password.value
  let score = 0
  if (p.length >= 8) score++
  if (p.length >= 12) score++
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) score++
  if (/\d/.test(p)) score++
  if (/[^A-Za-z0-9]/.test(p)) score++

  const levels = ['', t('auth.passwordStrength.weak'), t('auth.passwordStrength.fair'), t('auth.passwordStrength.good'), t('auth.passwordStrength.strong')]
  strength.level = Math.min(4, Math.max(1, score))
  strength.label = levels[strength.level]
}

async function handleRegister() {
  validateEmail()
  validatePassword()
  validateConfirm()
  if (errors.email || errors.password || errors.confirm) return

  serverError.value = ''
  loading.value = true
  try {
    await authStore.register(email.value, password.value, nickname.value || undefined)
    router.push('/dashboard')
  } catch (e: any) {
    const msg = e.response?.data?.detail
    if (typeof msg === 'string') {
      serverError.value = msg
    } else if (Array.isArray(msg)) {
      serverError.value = msg.map((m: any) => m.msg).join('；')
    } else {
      serverError.value = t('auth.registerFailed')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* Reuse login styles */
.auth-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--space-6);
  overflow: hidden;
}

.auth-bg { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.1;
}
.orb-1 {
  width: 500px; height: 500px;
  background: #818cf8;
  top: -150px; left: -100px;
  animation: float 9s ease-in-out infinite;
}
.orb-2 {
  width: 400px; height: 400px;
  background: var(--color-primary);
  bottom: -100px; right: -80px;
  animation: float 11s ease-in-out infinite reverse;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-25px); }
}

.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-lg);
}

.auth-header {
  text-align: center;
  margin-bottom: var(--space-6);
}
.auth-logo {
  font-size: 36px;
  margin-bottom: var(--space-2);
  filter: drop-shadow(0 0 10px rgba(99,102,241,0.35));
}
.auth-title {
  font-size: var(--text-2xl);
  font-weight: var(--weight-bold);
  background: linear-gradient(135deg, var(--color-text) 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.auth-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.auth-divider {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}
.auth-divider::before,
.auth-divider::after { content: ''; flex: 1; height: 1px; background: var(--color-border); }
.auth-divider span {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: var(--weight-medium);
}

.auth-form { display: flex; flex-direction: column; gap: var(--space-4); }
.form-field { display: flex; flex-direction: column; gap: var(--space-2); }
.form-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
}
.required { color: var(--color-error); }
.form-label-hint { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: normal; }

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
}
.input-suffix-btn:hover { color: var(--color-text); }

.input-error {
  border-color: var(--color-error) !important;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15) !important;
}
.field-error { font-size: var(--text-xs); color: var(--color-error); }

/* Password strength */
.strength-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
}
.strength-segment {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background: var(--color-border);
  transition: background var(--transition);
}
.strength-segment.active.level-1 { background: var(--color-error); }
.strength-segment.active.level-2 { background: var(--color-warning); }
.strength-segment.active.level-3 { background: #84cc16; }
.strength-segment.active.level-4 { background: var(--color-success); }
.strength-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  min-width: 28px;
}

/* Terms */
.terms-hint {
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
.terms-hint a { color: var(--color-text-secondary); }
.terms-hint a:hover { color: var(--color-primary); }

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

.slide-up-enter-active, .slide-up-leave-active { transition: all 0.2s ease; }
.slide-up-enter-from, .slide-up-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
