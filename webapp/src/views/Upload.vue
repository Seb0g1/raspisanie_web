<template>
  <div class="upload-page">
    <h1 class="page-title">Почта и расписания</h1>

    <div v-if="message" class="message" :class="messageClass">{{ message }}</div>

    <section class="card">
      <div class="card__header">
        <h2 class="section-title">Входящие письма</h2>
        <button class="btn btn--secondary" :disabled="scanLoading" @click="scanMail">
          {{ scanLoading ? 'Сканирование...' : 'Сканировать почту' }}
        </button>
      </div>

      <div v-if="emails.length === 0 && !scanLoading" class="empty">
        Нажмите «Сканировать почту», чтобы проверить входящие письма.
      </div>

      <div v-for="email in emails" :key="email.msg_id" class="email-item">
        <div class="email-header">
          <span class="email-date">{{ email.date }}</span>
          <span v-if="email.already_loaded" class="badge badge--loaded">Загружено</span>
          <span v-else-if="email.has_schedule_file" class="badge badge--word">{{ email.has_pdf ? 'PDF' : 'Word' }}</span>
        </div>
        <div class="email-subject">{{ email.subject || 'Без темы' }}</div>
        <div class="email-meta">
          <span>От: {{ email.sender }}</span>
          <span>Дата расписания: <strong>{{ email.schedule_date_formatted }}</strong></span>
        </div>
        <div v-if="email.attachments.length" class="email-attachments">
          <span v-for="att in email.attachments" :key="att.name" class="attachment-tag">
            {{ att.name }}
          </span>
        </div>
        <div class="email-actions">
          <button
            v-if="email.has_schedule_file"
            class="btn btn--small"
            :disabled="processingId === email.msg_id"
            @click="processEmail(email)"
          >
            {{ processingId === email.msg_id ? 'Обработка...' : (email.already_loaded ? 'Обновить' : 'Конвертировать и загрузить') }}
          </button>
          <label v-if="email.has_schedule_file" class="checkbox-label-small">
            <input type="checkbox" v-model="email._notify" />
            Уведомить
          </label>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card__header">
        <h2 class="section-title">Журнал обработки</h2>
        <button class="btn btn--secondary" :disabled="eventsLoading" @click="loadEvents">
          {{ eventsLoading ? 'Обновление...' : 'Обновить' }}
        </button>
      </div>

      <div v-if="mailEvents.length === 0 && !eventsLoading" class="empty">
        Событий пока нет.
      </div>

      <div v-for="event in mailEvents" :key="event.id" class="event-item" :class="'event-item--' + event.level">
        <div class="event-header">
          <span class="badge" :class="'badge--' + event.level">{{ event.level }}</span>
          <span class="event-type">{{ event.event_type }}</span>
          <span class="email-date">{{ formatEventDate(event.created_at) }}</span>
        </div>
        <div v-if="event.subject" class="email-subject">{{ event.subject }}</div>
        <div class="email-meta">
          <span v-if="event.schedule_date">Дата: {{ event.schedule_date }}</span>
          <span v-if="event.message_id">ID: {{ event.message_id }}</span>
        </div>
        <div class="event-detail">{{ event.detail }}</div>
      </div>
    </section>

    <section class="card">
      <h2 class="section-title">Загрузить вручную</h2>
      <p class="hint">PDF или Word-файл (.doc, .docx). Word автоматически конвертируется в PDF.</p>
      <form @submit.prevent="submit" class="form">
        <label class="label">Дата расписания</label>
        <input v-model="dateStr" type="date" class="input" required />

        <label class="label">Файл (PDF / DOC / DOCX)</label>
        <div
          class="drop-zone"
          :class="{ 'drop-zone--active': dragOver }"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
          @click="$refs.fileInput.click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".pdf,.doc,.docx"
            style="display: none"
            @change="onFileChange"
          />
          <span v-if="file">{{ file.name }} ({{ (file.size / 1024).toFixed(0) }} KB)</span>
          <span v-else class="drop-zone__hint">Нажмите или перетащите файл сюда</span>
        </div>

        <label class="checkbox-label">
          <input v-model="notify" type="checkbox" class="checkbox" />
          Уведомить подписчиков
        </label>

        <button type="submit" class="btn btn--primary" :disabled="uploadLoading">
          {{ uploadLoading ? 'Загрузка...' : 'Загрузить' }}
        </button>
      </form>
    </section>

    <section class="card">
      <h2 class="section-title">Архив расписаний</h2>
      <div v-if="schedules.length === 0" class="empty">Архив пуст</div>
      <div v-else class="schedule-list">
        <a
          v-for="s in schedules"
          :key="s.date"
          :href="'/schedule/' + s.date + '.pdf'"
          target="_blank"
          class="schedule-item"
        >
          {{ s.date_formatted }}
        </a>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const message = ref('')
const messageClass = ref('')

const scanLoading = ref(false)
const emails = ref([])
const processingId = ref(null)

const eventsLoading = ref(false)
const mailEvents = ref([])

const dateStr = ref('')
const file = ref(null)
const notify = ref(false)
const uploadLoading = ref(false)
const dragOver = ref(false)

const schedules = ref([])

function showMessage(text, type = 'success') {
  message.value = text
  messageClass.value = type === 'error' ? 'message--error' : 'message--success'
  setTimeout(() => { message.value = '' }, 8000)
}

function formatEventDate(value) {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 19)
}

async function scanMail() {
  scanLoading.value = true
  message.value = ''
  try {
    const data = await api.mailScan()
    emails.value = (data.items || []).map(e => ({ ...e, _notify: false }))
    showMessage(emails.value.length ? `Найдено писем: ${emails.value.length}` : 'Писем не найдено')
    await loadEvents()
  } catch (e) {
    showMessage(e.message || 'Ошибка сканирования почты', 'error')
  } finally {
    scanLoading.value = false
  }
}

async function processEmail(email) {
  processingId.value = email.msg_id
  try {
    const res = await api.mailProcess(email.msg_id, email._notify || false)
    email.already_loaded = true
    showMessage(`Расписание на ${res.schedule_date} загружено (${res.processed} файл(ов))`)
    await loadSchedules()
    await loadEvents()
  } catch (e) {
    showMessage(e.message || 'Ошибка обработки письма', 'error')
    await loadEvents()
  } finally {
    processingId.value = null
  }
}

function onFileChange(e) {
  file.value = e.target.files[0] || null
}

function onDrop(e) {
  dragOver.value = false
  const dropped = e.dataTransfer.files[0]
  if (dropped) file.value = dropped
}

async function loadSchedules() {
  try {
    const data = await api.schedules()
    schedules.value = data.items || []
  } catch (_) {}
}

async function loadEvents() {
  eventsLoading.value = true
  try {
    const data = await api.mailEvents()
    mailEvents.value = data.items || []
  } catch (_) {
  } finally {
    eventsLoading.value = false
  }
}

async function submit() {
  if (!dateStr.value || !file.value) {
    showMessage('Укажите дату и выберите файл', 'error')
    return
  }
  uploadLoading.value = true
  try {
    const fd = new FormData()
    fd.append('date', dateStr.value)
    fd.append('file', file.value)
    if (notify.value) fd.append('notify', 'true')
    const res = await api.uploadSchedule(fd)
    const parts = [`Расписание на ${res.date} загружено`]
    if (res.converted_from_word) parts.push('Word -> PDF')
    if (res.parsed_groups) parts.push(`групп распознано: ${res.parsed_groups}`)
    if (res.notified) parts.push(`уведомлено: ${res.notified}`)
    showMessage(parts.join(' · '))
    file.value = null
    dateStr.value = ''
    notify.value = false
    await loadSchedules()
    await loadEvents()
  } catch (e) {
    showMessage(e.message || 'Ошибка загрузки', 'error')
    await loadEvents()
  } finally {
    uploadLoading.value = false
  }
}

onMounted(() => {
  loadSchedules()
  loadEvents()
})
</script>

<style scoped>
.upload-page { display: flex; flex-direction: column; gap: 1.5rem; }
.page-title { font-family: var(--font-sans); font-size: 1.5rem; font-weight: 600; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
}
.card__header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.section-title { font-family: var(--font-sans); font-size: 1.1rem; font-weight: 600; margin-bottom: 0.75rem; }
.card__header .section-title { margin-bottom: 0; }
.hint { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 0.75rem; }
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.label { font-size: 0.85rem; color: var(--text-muted); }
.input {
  font-family: var(--font-mono); font-size: 0.9rem; padding: 0.6rem 0.75rem;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text); outline: none;
}
.input:focus { border-color: var(--accent); }
.email-item, .event-item {
  border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem;
  margin-bottom: 0.5rem; background: var(--bg-input);
}
.event-item--error { border-color: rgba(255,71,87,0.5); }
.event-item--warning { border-color: rgba(255,193,7,0.5); }
.email-header, .event-header { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.25rem; }
.email-date { font-size: 0.8rem; color: var(--text-muted); }
.email-subject { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
.email-meta { font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 1rem; flex-wrap: wrap; }
.email-attachments { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.5rem; }
.attachment-tag {
  font-size: 0.75rem; padding: 0.2rem 0.5rem; background: rgba(0,212,170,0.1);
  border: 1px solid rgba(0,212,170,0.3); border-radius: 4px; color: var(--accent);
}
.email-actions { display: flex; align-items: center; gap: 0.75rem; margin-top: 0.5rem; }
.event-type { font-weight: 600; }
.event-detail { color: var(--text-muted); font-size: 0.85rem; white-space: pre-wrap; margin-top: 0.35rem; }
.badge {
  font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 4px; font-weight: 600;
  background: rgba(255,255,255,0.08); color: var(--text-muted);
}
.badge--loaded, .badge--info { background: rgba(0,212,170,0.2); color: var(--accent); }
.badge--word { background: rgba(66,133,244,0.2); color: #4285f4; }
.badge--warning { background: rgba(255,193,7,0.18); color: #ffc107; }
.badge--error { background: rgba(255,71,87,0.18); color: var(--danger); }
.drop-zone {
  border: 2px dashed var(--border); border-radius: 8px; padding: 2rem;
  text-align: center; cursor: pointer; transition: border-color 0.2s, background 0.2s;
  color: var(--text-muted); font-size: 0.9rem;
}
.drop-zone:hover, .drop-zone--active { border-color: var(--accent); background: rgba(0,212,170,0.05); }
.drop-zone__hint { opacity: 0.7; }
.checkbox-label, .checkbox-label-small {
  display: flex; align-items: center; gap: 0.5rem; color: var(--text); cursor: pointer;
}
.checkbox-label { font-size: 0.9rem; }
.checkbox-label-small { font-size: 0.8rem; color: var(--text-muted); }
.checkbox { width: 1rem; height: 1rem; accent-color: var(--accent); }
.btn {
  font-family: var(--font-mono); font-size: 0.9rem; padding: 0.6rem 1rem;
  border: 1px solid var(--border); border-radius: 8px; cursor: pointer;
  transition: all 0.2s; background: var(--bg-input); color: var(--text);
}
.btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn--primary { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
.btn--primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn--small { font-size: 0.8rem; padding: 0.4rem 0.75rem; }
.message { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; }
.message--error { background: rgba(255,71,87,0.15); color: var(--danger); }
.message--success { background: rgba(0,212,170,0.15); color: var(--accent); }
.empty { color: var(--text-muted); font-size: 0.9rem; }
.schedule-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.schedule-item {
  display: inline-block; padding: 0.4rem 0.75rem; background: var(--bg-input);
  border: 1px solid var(--border); border-radius: 8px; color: var(--text);
  text-decoration: none; font-size: 0.85rem; transition: border-color 0.2s, color 0.2s;
}
.schedule-item:hover { border-color: var(--accent); color: var(--accent); }
</style>
