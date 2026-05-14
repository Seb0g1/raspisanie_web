<template>
  <div class="broadcast">
    <h1 class="page-title">Рассылка</h1>
    <p class="subtitle">Текст и/или фото уйдут всем подписчикам без подписи.</p>
    <div class="card">
      <form @submit.prevent="submit">
        <label class="label">Текст сообщения</label>
        <textarea
          v-model="message"
          class="textarea"
          rows="4"
          placeholder="Введите текст..."
        />
        <label class="label">Фото (необязательно)</label>
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          multiple
          class="file-input"
          @change="onFileChange"
        />
        <div v-if="previewFiles.length" class="preview-wrap">
          <p class="label">Предпросмотр поста</p>
          <div class="preview">
            <div class="preview-text" v-if="message.trim()">{{ message.trim() }}</div>
            <div v-if="!message.trim() && previewFiles.length" class="preview-text preview-text--muted">Только фото</div>
            <div class="preview-thumbs">
              <img
                v-for="(url, i) in previewUrls"
                :key="i"
                :src="url"
                alt=""
                class="preview-thumb"
              />
            </div>
          </div>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="result" class="result">{{ result }}</p>
        <button type="submit" class="btn" :disabled="loading">
          {{ loading ? 'Отправка…' : 'Отправить всем' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'

const message = ref('')
const fileInput = ref(null)
const previewFiles = ref([])
const previewUrls = ref([])
const error = ref('')
const result = ref('')
const loading = ref(false)

function revokeUrls() {
  previewUrls.value.forEach((u) => URL.revokeObjectURL(u))
  previewUrls.value = []
}

function onFileChange(e) {
  revokeUrls()
  const files = Array.from(e.target.files || [])
  previewFiles.value = files.filter((f) => f.type.startsWith('image/'))
  previewUrls.value = previewFiles.value.map((f) => URL.createObjectURL(f))
}

watch(previewFiles, () => {
  if (!previewFiles.value.length) revokeUrls()
})

async function submit() {
  error.value = ''
  result.value = ''
  const text = message.value.trim()
  const files = previewFiles.value
  if (!text && !files.length) {
    error.value = 'Введите текст и/или приложите фото'
    return
  }
  loading.value = true
  try {
    let data
    if (files.length) {
      const form = new FormData()
      form.append('message', text)
      files.forEach((f) => form.append('photos', f))
      data = await api.broadcastWithFiles(form)
    } else {
      data = await api.broadcast(text)
    }
    result.value = `Разослано: ${data.sent}, ошибок: ${data.failed}.`
    message.value = ''
    previewFiles.value = []
    revokeUrls()
    if (fileInput.value) fileInput.value.value = ''
  } catch (e) {
    error.value = e.message || 'Ошибка рассылки'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.broadcast { display: flex; flex-direction: column; gap: 1rem; }
.page-title {
  font-family: var(--font-sans);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text);
}
.subtitle { font-size: 0.9rem; color: var(--text-muted); }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
}
.label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; }
.textarea {
  font-family: var(--font-mono);
  font-size: 0.95rem;
  width: 100%;
  padding: 0.75rem 1rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
  margin-bottom: 1rem;
}
.textarea:focus { border-color: var(--accent); }
.file-input {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  margin-bottom: 1rem;
  color: var(--text-muted);
}
.preview-wrap { margin-bottom: 1rem; }
.preview {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
}
.preview-text {
  font-size: 0.95rem;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 0.75rem;
}
.preview-text--muted { color: var(--text-muted); }
.preview-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.preview-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.error { font-size: 0.9rem; color: var(--danger); margin-bottom: 0.5rem; }
.result { font-size: 0.9rem; color: var(--accent); margin-bottom: 0.5rem; }
.btn {
  font-family: var(--font-mono);
  font-size: 0.95rem;
  padding: 0.75rem 1.25rem;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.btn:hover:not(:disabled) { background: var(--accent-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
