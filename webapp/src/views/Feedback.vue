<template>
  <div class="feedback-page">
    <h1 class="page-title">Обратная связь</h1>
    <p class="subtitle">Ответ пользователю отправляется без подписи — только ваш текст.</p>
    <div v-if="error" class="message message--error">{{ error }}</div>
    <div v-if="loading && !items.length" class="loading">Загрузка…</div>
    <div v-else-if="!items.length" class="empty">Пока нет обращений.</div>
    <div v-else class="list">
      <div v-for="item in items" :key="item.id" class="item">
        <div class="item__meta">#{{ item.id }} · {{ item.user_info }} · {{ item.created_at }}</div>
        <div class="item__text">{{ item.text }}</div>
        <div v-if="item.reply_text" class="item__replied">
          Ответ: {{ item.reply_text.slice(0, 80) }}{{ item.reply_text.length > 80 ? '…' : '' }} ({{ item.replied_at }})
        </div>
        <form v-else class="reply-form" @submit.prevent="reply(item.id)">
          <textarea
            v-model="replies[item.id]"
            class="textarea"
            rows="2"
            placeholder="Ответ (без подписи)"
            required
          />
          <button type="submit" class="btn btn--small" :disabled="sending === item.id">
            {{ sending === item.id ? 'Отправка…' : 'Ответить' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api'

const items = ref([])
const replies = reactive({})
const error = ref('')
const loading = ref(true)
const sending = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await api.feedback()
    items.value = data.items || []
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

async function reply(id) {
  const text = (replies[id] || '').trim()
  if (!text) return
  sending.value = id
  try {
    await api.feedbackReply(id, text)
    replies[id] = ''
    await load()
  } catch (e) {
    error.value = e.message || 'Ошибка отправки'
  } finally {
    sending.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.feedback-page { display: flex; flex-direction: column; gap: 1rem; }
.page-title {
  font-family: var(--font-sans);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text);
}
.subtitle { font-size: 0.9rem; color: var(--text-muted); }
.loading, .empty { color: var(--text-muted); font-size: 0.9rem; }
.message { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; }
.message--error { background: rgba(255, 71, 87, 0.15); color: var(--danger); }
.list { display: flex; flex-direction: column; gap: 1rem; }
.item {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
}
.item__meta { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem; }
.item__text { margin-bottom: 0.75rem; font-size: 0.95rem; }
.item__replied { font-size: 0.8rem; color: var(--text-muted); }
.reply-form { margin-top: 0.75rem; }
.textarea {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  width: 100%;
  padding: 0.6rem 0.75rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  resize: vertical;
  outline: none;
  margin-bottom: 0.5rem;
}
.textarea:focus { border-color: var(--accent); }
.btn {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  padding: 0.5rem 1rem;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.btn:hover:not(:disabled) { background: var(--accent-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn--small { }
</style>
