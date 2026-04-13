<template>
  <div class="page">
      <!-- Header -->
      <div class="page-header">
        <div>
          <h1>我的项目</h1>
          <p class="page-subtitle">{{ projects.length }} 个项目</p>
        </div>
        <button class="btn btn-primary" @click="openCreateModal">
          <span>＋</span> 新建项目
        </button>
      </div>

      <!-- Loading -->
      <div v-if="projectStore.loading" class="center-container">
        <LoadingSpinner size="lg" label="加载中…" />
      </div>

      <!-- Empty state -->
      <div v-else-if="projects.length === 0" class="empty-state">
        <div class="empty-icon">🎬</div>
        <p>还没有项目</p>
        <small>创建你的第一个 AI 剪辑项目，开始创作之旅</small>
        <button class="btn btn-primary mt-4" @click="openCreateModal">创建项目</button>
      </div>

      <!-- Project grid -->
      <div v-else class="project-grid">
        <div
          v-for="p in projects"
          :key="p.id"
          class="project-card"
          @click="openProject(p.id)"
          role="button"
          tabindex="0"
          @keyup.enter="openProject(p.id)"
        >
          <!-- Card top -->
          <div class="project-card-top">
            <div class="project-thumb">{{ projectEmoji(p.status) }}</div>
            <div :class="['badge', `badge-${p.status}`]">{{ statusLabel(p.status) }}</div>
          </div>

          <!-- Card body -->
          <div class="project-card-body">
            <h3 class="project-name">{{ p.name }}</h3>
            <p class="project-desc">{{ p.description || '暂无描述' }}</p>
          </div>

          <!-- Card footer -->
          <div class="project-card-footer">
            <span class="project-date">{{ formatDate(p.created_at) }}</span>
            <div class="card-actions" @click.stop>
              <button
                class="btn btn-ghost btn-sm"
                title="继续编辑"
                @click="openProject(p.id)"
              >编辑</button>
              <button
                class="btn btn-danger btn-sm"
                title="删除项目"
                @click="confirmDelete(p)"
              >删除</button>
            </div>
          </div>
        </div>
      </div>

    <!-- Create modal -->
    <Transition name="fade">
      <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
        <div class="modal" @keyup.esc="showCreate = false">
          <div class="modal-header">
            <h2 class="modal-title">新建项目</h2>
            <button class="modal-close" @click="showCreate = false">✕</button>
          </div>

          <form @submit.prevent="createProject">
            <div class="form-field">
              <label class="form-label" for="create-name">项目名称 <span class="required">*</span></label>
              <input
                id="create-name"
                v-model="newName"
                type="text"
                class="input"
                placeholder="例如：产品发布会宣传片"
                maxlength="60"
                autofocus
                required
              />
              <span class="char-hint">{{ newName.length }} / 60</span>
            </div>

            <div class="form-field mt-4">
              <label class="form-label" for="create-desc">项目描述</label>
              <textarea
                id="create-desc"
                v-model="newDesc"
                class="input"
                placeholder="简单描述这个视频的用途…（可选）"
                rows="3"
                maxlength="200"
              />
            </div>

            <div class="modal-footer">
              <button type="button" class="btn btn-ghost" @click="showCreate = false">取消</button>
              <button
                type="submit"
                class="btn btn-primary"
                :disabled="!newName.trim() || creating"
              >
                <span v-if="creating" class="btn-spinner" />
                {{ creating ? '创建中…' : '创建并开始' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>

    <!-- Delete confirm modal -->
    <Transition name="fade">
      <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
        <div class="modal modal-sm">
          <div class="modal-header">
            <h2 class="modal-title danger-title">删除项目</h2>
            <button class="modal-close" @click="deleteTarget = null">✕</button>
          </div>

          <p class="delete-confirm-text">
            确定要删除项目 <strong>「{{ deleteTarget.name }}」</strong> 吗？
          </p>
          <p class="delete-warn">此操作不可撤销，相关视频文件和剪辑结果将一并删除。</p>

          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" @click="deleteTarget = null">取消</button>
            <button
              type="button"
              class="btn btn-danger"
              :disabled="deleting"
              @click="doDelete"
            >
              <span v-if="deleting" class="btn-spinner btn-spinner-red" />
              {{ deleting ? '删除中…' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import type { Project } from '@/types'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const router = useRouter()
const projectStore = useProjectStore()

const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')
const creating = ref(false)

const deleteTarget = ref<Project | null>(null)
const deleting = ref(false)

const projects = computed(() => projectStore.projects)

onMounted(() => projectStore.fetchProjects())

function openCreateModal() {
  newName.value = ''
  newDesc.value = ''
  showCreate.value = true
}

async function createProject() {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    const p = await projectStore.createProject(newName.value.trim(), newDesc.value || undefined)
    showCreate.value = false
    router.push(`/project/${p.id}/guide`)
  } catch (e) {
    // TODO: show toast
    console.error(e)
  } finally {
    creating.value = false
  }
}

function openProject(id: string) {
  router.push(`/project/${id}/guide`)
}

function confirmDelete(p: Project) {
  deleteTarget.value = p
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await projectStore.deleteProject(deleteTarget.value.id)
    deleteTarget.value = null
  } catch (e) {
    console.error(e)
  } finally {
    deleting.value = false
  }
}

const statusMap: Record<string, string> = {
  draft: '草稿',
  scripting: '编写剧本',
  clipping: '剪辑中',
  done: '已完成',
}
function statusLabel(s: string) { return statusMap[s] || s }

const emojiMap: Record<string, string> = {
  draft: '📝',
  scripting: '✍️',
  clipping: '✂️',
  done: '🎉',
}
function projectEmoji(s: string) { return emojiMap[s] || '🎬' }

function formatDate(d: string) {
  const date = new Date(d)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.page-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

/* Grid */
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-5);
}

/* Card */
.project-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.project-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.3), 0 0 0 1px var(--color-primary-light);
}
.project-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.project-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.project-thumb {
  width: 44px;
  height: 44px;
  border-radius: var(--radius);
  background: var(--color-primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.project-card-body { flex: 1; }

.project-name {
  font-size: var(--text-base);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.5;
  min-height: 42px;
}

.project-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.project-date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.card-actions {
  display: flex;
  gap: var(--space-2);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.project-card:hover .card-actions { opacity: 1; }

/* Center container */
.center-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

/* Create form */
.form-field { display: flex; flex-direction: column; gap: var(--space-2); }
.form-label {
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.required { color: var(--color-error); }
.char-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: right;
}

/* Delete modal */
.modal-sm { max-width: 400px; }
.danger-title { color: var(--color-error); }
.delete-confirm-text {
  font-size: var(--text-base);
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.delete-confirm-text strong { color: var(--color-text); }
.delete-warn {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Spinner */
.btn-spinner {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}
.btn-spinner-red {
  border-color: rgba(239,68,68,0.3);
  border-top-color: var(--color-error);
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
