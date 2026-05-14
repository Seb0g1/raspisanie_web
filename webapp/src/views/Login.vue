<template>
  <div class="login">
    <div class="card">
      <h1 class="title">Вход в панель</h1>
      <p class="subtitle">Бот расписания СП ЦПСУ «ЭНЕРГИЯ»</p>
      <form @submit.prevent="submit" class="form">
        <label class="label">Пароль</label>
        <input
          v-model="password"
          type="password"
          class="input"
          placeholder="Введите пароль"
          autocomplete="current-password"
          autofocus
        />
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn" :disabled="loading">
          {{ loading ? 'Вход…' : 'Войти' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const route = useRoute()
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  if (!password.value.trim()) return
  loading.value = true
  try {
    await api.login(password.value)
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch (e) {
    error.value = e.message || 'Ошибка входа'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  password.value = ''
  error.value = ''
})
</script>

<style scoped>
.login { width: 100%; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2rem;
}
.title {
  font-family: var(--font-sans);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 0.25rem;
}
.subtitle {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 1.5rem;
}
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.label {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.input {
  font-family: var(--font-mono);
  font-size: 1rem;
  padding: 0.75rem 1rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  outline: none;
  transition: border-color 0.2s;
}
.input:focus { border-color: var(--accent); }
.input::placeholder { color: var(--text-muted); opacity: 0.7; }
.error {
  font-size: 0.85rem;
  color: var(--danger);
}
.btn {
  font-family: var(--font-mono);
  font-size: 0.95rem;
  font-weight: 500;
  padding: 0.75rem 1.25rem;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: background 0.2s;
}
.btn:hover:not(:disabled) { background: var(--accent-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
