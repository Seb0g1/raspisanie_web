<template>
  <section class="users">
    <div class="page-head">
      <div>
        <h1>Пользователи</h1>
        <p>Группы, активность и настройки уведомлений.</p>
      </div>
      <button type="button" class="btn-secondary" :disabled="loading" @click="load">
        Обновить
      </button>
    </div>

    <div v-if="error" class="alert">{{ error }}</div>

    <div class="stats-grid">
      <article v-for="group in groupStats" :key="group.group_code" class="stat-card">
        <div class="stat-title">{{ group.group_code }}</div>
        <div class="stat-value">{{ group.users_count }}</div>
        <div class="stat-meta">
          Уведомления: {{ group.notifications_enabled_count }} · Активны 7 дней: {{ group.active_7_count }}
        </div>
        <div v-if="group.missing_count" class="stat-warning">
          Не найдена группа: {{ group.missing_count }}
        </div>
      </article>
    </div>

    <div class="toolbar">
      <label>
        Поиск
        <input v-model.trim="query" type="search" placeholder="chat id или группа">
      </label>
      <button type="button" class="btn-secondary" :disabled="cleanupBusy" @click="cleanup">
        Очистить тех. таблицы
      </button>
    </div>

    <div v-if="cleanupResult" class="notice">
      Удалено: processed_updates {{ cleanupResult.deleted.processed_updates || 0 }},
      mail_events {{ cleanupResult.deleted.mail_events || 0 }},
      sent_schedule_notifications {{ cleanupResult.deleted.sent_schedule_notifications || 0 }},
      subscriber_group_history {{ cleanupResult.deleted.subscriber_group_history || 0 }}.
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Chat ID</th>
            <th>Группа</th>
            <th>Уведомления</th>
            <th>Первый запуск</th>
            <th>Активность</th>
            <th>Проблемы</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in filteredUsers" :key="user.chat_id">
            <td>{{ user.chat_id }}</td>
            <td>
              <span class="group-pill" :class="{ muted: !user.group_code }">
                {{ user.group_code || 'Без группы' }}
              </span>
            </td>
            <td>
              <span :class="user.notifications_enabled ? 'ok' : 'muted'">
                {{ user.notifications_enabled ? 'включены' : 'выключены' }}
              </span>
            </td>
            <td>{{ formatDate(user.first_seen) }}</td>
            <td>{{ formatDate(user.last_activity) }}</td>
            <td>
              <span v-if="user.group_missing_count" class="warning">
                группа не найдена: {{ user.group_missing_count }}
              </span>
              <span v-else class="muted">нет</span>
            </td>
          </tr>
          <tr v-if="!loading && filteredUsers.length === 0">
            <td colspan="6" class="empty">Пользователи не найдены</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const users = ref([])
const groupStats = ref([])
const loading = ref(false)
const cleanupBusy = ref(false)
const cleanupResult = ref(null)
const error = ref('')
const query = ref('')

const filteredUsers = computed(() => {
  const q = query.value.toLowerCase()
  if (!q) return users.value
  return users.value.filter((user) => {
    return String(user.chat_id).includes(q) || String(user.group_code || '').toLowerCase().includes(q)
  })
})

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.users()
    users.value = data.items || []
    groupStats.value = data.group_stats || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function cleanup() {
  cleanupBusy.value = true
  error.value = ''
  try {
    cleanupResult.value = await api.cleanup(90)
  } catch (e) {
    error.value = e.message
  } finally {
    cleanupBusy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.users { display: grid; gap: 1.25rem; }
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}
h1 {
  font-family: var(--font-sans);
  font-size: 1.75rem;
  letter-spacing: 0;
}
p { color: var(--text-muted); margin-top: 0.25rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
}
.stat-title { color: var(--text-muted); font-size: 0.85rem; }
.stat-value { font-family: var(--font-sans); font-size: 2rem; margin-top: 0.25rem; }
.stat-meta { color: var(--text-muted); font-size: 0.8rem; margin-top: 0.25rem; }
.stat-warning, .warning { color: #ffb86b; }
.toolbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}
label {
  display: grid;
  gap: 0.4rem;
  color: var(--text-muted);
  font-size: 0.8rem;
  width: min(360px, 100%);
}
input {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text);
  font: inherit;
}
.btn-secondary {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.btn-secondary:disabled { opacity: 0.6; cursor: wait; }
.alert, .notice {
  padding: 0.85rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-card);
}
.alert { color: var(--danger); }
.notice { color: var(--accent); }
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 820px;
}
th, td {
  padding: 0.85rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 0.85rem;
}
th {
  color: var(--text-muted);
  font-weight: 600;
  background: var(--bg-card);
}
tr:last-child td { border-bottom: 0; }
.group-pill {
  display: inline-flex;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.ok { color: var(--accent); }
.muted { color: var(--text-muted); }
.empty { color: var(--text-muted); text-align: center; }
@media (max-width: 760px) {
  .page-head, .toolbar { align-items: stretch; flex-direction: column; }
}
</style>
