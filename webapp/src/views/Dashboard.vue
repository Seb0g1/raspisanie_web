<template>
  <div class="dashboard">
    <h1 class="page-title">Главная</h1>
    <div v-if="error" class="message message--error">{{ error }}</div>
    <div v-if="stats" class="stats">
      <div class="stat">
        <span class="stat__value">{{ stats.total }}</span>
        <span class="stat__label">Подписчиков</span>
      </div>
      <div class="stat">
        <span class="stat__value">{{ stats.new_7 }}</span>
        <span class="stat__label">Новых за 7 дней</span>
      </div>
      <div class="stat">
        <span class="stat__value">{{ stats.active_7 }}</span>
        <span class="stat__label">Активных за 7 дней</span>
      </div>
      <div class="stat">
        <span class="stat__value">{{ stats.schedules_count }}</span>
        <span class="stat__label">Расписаний в архиве</span>
      </div>
    </div>
    <div class="card card--info">
      <p>Рассылка — сообщение уходит без подписи. Ответы на обратную связь — только ваш текст.</p>
      <button
        type="button"
        class="btn btn--secondary"
        :disabled="checkmailLoading"
        @click="checkmail"
      >
        {{ checkmailLoading ? 'Проверка…' : 'Проверить почту (расписания)' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const stats = ref(null)
const error = ref('')
const checkmailLoading = ref(false)

async function load() {
  try {
    stats.value = await api.stats()
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Ошибка загрузки'
  }
}

async function checkmail() {
  checkmailLoading.value = true
  try {
    await api.checkmail()
    await load()
  } catch (e) {
    error.value = e.message || 'Ошибка проверки почты'
  } finally {
    checkmailLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 1.5rem; }
.page-title {
  font-family: var(--font-sans);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text);
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1rem;
}
.stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  text-align: center;
}
.stat__value {
  display: block;
  font-size: 2rem;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 0.25rem;
}
.stat__label { font-size: 0.8rem; color: var(--text-muted); }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
}
.card--info p { margin-bottom: 1rem; color: var(--text-muted); font-size: 0.9rem; }
.message { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; }
.message--error { background: rgba(255, 71, 87, 0.15); color: var(--danger); }
.btn {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  padding: 0.6rem 1rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn--secondary { }
</style>
