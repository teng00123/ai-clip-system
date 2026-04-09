<template>
  <nav class="navbar">
    <div class="navbar-inner">
      <!-- Logo -->
      <RouterLink to="/dashboard" class="navbar-logo">
        <span class="logo-icon">✂️</span>
        <span class="logo-text">AI Clip</span>
      </RouterLink>

      <!-- Project breadcrumb (shown when inside a project) -->
      <div v-if="currentProject" class="navbar-breadcrumb">
        <span class="breadcrumb-sep">›</span>
        <RouterLink to="/dashboard" class="breadcrumb-link">项目</RouterLink>
        <span class="breadcrumb-sep">›</span>
        <span class="breadcrumb-current">{{ currentProject.name }}</span>
      </div>

      <!-- Step tabs (shown inside project) -->
      <div v-if="currentProject" class="navbar-steps">
        <RouterLink
          v-for="step in steps"
          :key="step.path"
          :to="`/project/${projectId}/${step.path}`"
          :class="['step-link', { active: isActiveStep(step.path) }]"
        >
          <span class="step-num">{{ step.num }}</span>
          {{ step.label }}
        </RouterLink>
      </div>

      <div class="navbar-right">
        <!-- User menu -->
        <div class="user-menu" @click="menuOpen = !menuOpen" ref="menuRef">
          <div class="user-avatar">
            {{ userInitial }}
          </div>
          <span class="user-name">{{ authStore.user?.nickname || authStore.user?.email }}</span>
          <span class="menu-arrow" :class="{ open: menuOpen }">▾</span>

          <Transition name="fade">
            <div v-if="menuOpen" class="dropdown">
              <div class="dropdown-header">
                <span class="dropdown-email">{{ authStore.user?.email }}</span>
              </div>
              <div class="dropdown-divider" />
              <button class="dropdown-item danger" @click="handleLogout">
                退出登录
              </button>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const projectStore = useProjectStore()

const menuOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)

const projectId = computed(() => route.params.projectId as string | undefined)
const currentProject = computed(() => {
  if (!projectId.value) return null
  return projectStore.currentProject
})

const userInitial = computed(() => {
  const name = authStore.user?.nickname || authStore.user?.email || '?'
  return name.charAt(0).toUpperCase()
})

const steps = [
  { num: '1', label: '问答引导', path: 'guide' },
  { num: '2', label: '剧本编辑', path: 'script' },
  { num: '3', label: '上传视频', path: 'upload' },
  { num: '4', label: 'AI 剪辑', path: 'clip' },
  { num: '5', label: '导出', path: 'export' },
]

function isActiveStep(path: string) {
  return route.path.includes(`/${path}`)
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

// Close dropdown on outside click
function handleOutsideClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    menuOpen.value = false
  }
}
onMounted(() => document.addEventListener('click', handleOutsideClick))
onUnmounted(() => document.removeEventListener('click', handleOutsideClick))

// Fetch project when inside project route
onMounted(async () => {
  if (projectId.value && !projectStore.currentProject) {
    try {
      await projectStore.selectProject(projectId.value)
    } catch {}
  }
})
</script>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--navbar-height);
  background: rgba(15, 17, 23, 0.92);
  border-bottom: 1px solid var(--color-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.navbar-inner {
  max-width: var(--content-max);
  height: 100%;
  margin: 0 auto;
  padding: 0 var(--space-6);
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

/* Logo */
.navbar-logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  flex-shrink: 0;
}
.logo-icon { font-size: 20px; }
.logo-text {
  font-size: var(--text-base);
  font-weight: var(--weight-bold);
  color: var(--color-text);
  letter-spacing: -0.02em;
}

/* Breadcrumb */
.navbar-breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  flex-shrink: 0;
}
.breadcrumb-sep { color: var(--color-text-muted); }
.breadcrumb-link { color: var(--color-text-secondary); }
.breadcrumb-link:hover { color: var(--color-text); }
.breadcrumb-current {
  color: var(--color-text);
  font-weight: var(--weight-medium);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Step tabs */
.navbar-steps {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex: 1;
}
.step-link {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-decoration: none;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.step-link:hover {
  color: var(--color-text);
  background: var(--color-bg-hover);
}
.step-link.active {
  color: var(--color-primary);
  background: var(--color-primary-light);
  font-weight: var(--weight-medium);
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 10px;
  background: var(--color-border);
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.step-link.active .step-num {
  background: var(--color-primary);
  color: #fff;
}

/* User menu */
.navbar-right { margin-left: auto; flex-shrink: 0; }

.user-menu {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3) var(--space-1) var(--space-1);
  border-radius: var(--radius-full);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
  user-select: none;
}
.user-menu:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border);
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-primary), #818cf8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: var(--weight-bold);
  color: #fff;
  flex-shrink: 0;
}

.user-name {
  font-size: var(--text-sm);
  color: var(--color-text);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-arrow {
  font-size: 10px;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
}
.menu-arrow.open { transform: rotate(180deg); }

/* Dropdown */
.dropdown {
  position: absolute;
  top: calc(100% + var(--space-2));
  right: 0;
  min-width: 200px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  z-index: 100;
}

.dropdown-header {
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-2);
}
.dropdown-email {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-divider { height: 1px; background: var(--color-border); }

.dropdown-item {
  display: block;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  font-size: var(--text-sm);
  color: var(--color-text);
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-fast);
  font-family: var(--font-sans);
}
.dropdown-item:hover { background: var(--color-bg-hover); }
.dropdown-item.danger { color: var(--color-error); }
.dropdown-item.danger:hover { background: rgba(239,68,68,0.1); }

/* Responsive: hide step labels on small screens */
@media (max-width: 768px) {
  .navbar-breadcrumb { display: none; }
  .navbar-steps { display: none; }
  .user-name { display: none; }
}
</style>
