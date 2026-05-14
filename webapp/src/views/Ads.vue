<template>
  <div class="ads">
    <h1 class="page-title">Реклама</h1>
    <p class="subtitle">Создайте рекламный пост с HTML-форматированием, эмодзи, баннером и кнопкой.</p>

    <div class="card">
      <form @submit.prevent="submit">
        <!-- Formatting toolbar -->
        <label class="label">Текст сообщения (HTML)</label>
        <div class="toolbar">
          <button type="button" class="tb-btn" title="Bold" @click="wrapTag('b')"><b>B</b></button>
          <button type="button" class="tb-btn" title="Italic" @click="wrapTag('i')"><i>I</i></button>
          <button type="button" class="tb-btn" title="Underline" @click="wrapTag('u')"><u>U</u></button>
          <button type="button" class="tb-btn" title="Strikethrough" @click="wrapTag('s')"><s>S</s></button>
          <button type="button" class="tb-btn" title="Code" @click="wrapTag('code')">&lt;/&gt;</button>
          <button type="button" class="tb-btn" title="Link" @click="insertLink">Link</button>
          <span class="tb-sep"></span>
          <button type="button" class="tb-btn" :class="{ active: showEmoji }" title="Emoji" @click="showEmoji = !showEmoji">😀</button>
          <button type="button" class="tb-btn" :class="{ active: showCustomEmoji }" title="Custom Emoji" @click="showCustomEmoji = !showCustomEmoji">⭐</button>
        </div>

        <textarea
          ref="textareaRef"
          v-model="message"
          class="textarea"
          rows="6"
          placeholder="Введите текст с HTML тегами..."
        />
        <div class="char-count" :class="{ warn: photoFile && message.length > 1024 }">
          {{ message.length }}{{ photoFile ? ' / 1024' : '' }} символов
        </div>

        <!-- Emoji picker -->
        <div v-if="showEmoji" class="emoji-panel">
          <div class="emoji-tabs">
            <button
              v-for="cat in emojiCategories"
              :key="cat.name"
              type="button"
              class="emoji-tab"
              :class="{ active: activeEmojiCat === cat.name }"
              @click="activeEmojiCat = cat.name"
            >{{ cat.icon }}</button>
          </div>
          <div class="emoji-grid">
            <button
              v-for="em in currentEmojis"
              :key="em"
              type="button"
              class="emoji-item"
              @click="insertEmoji(em)"
            >{{ em }}</button>
          </div>
        </div>

        <!-- Custom emoji -->
        <div v-if="showCustomEmoji" class="custom-emoji-panel">
          <label class="label">Telegram Premium Emoji ID</label>
          <div class="custom-emoji-row">
            <input
              v-model="customEmojiId"
              class="input"
              placeholder="5368324170671202286"
            />
            <input
              v-model="customEmojiAlt"
              class="input input--small"
              placeholder="Alt text"
            />
            <button type="button" class="btn btn--sm" @click="insertCustomEmoji">Вставить</button>
          </div>
        </div>

        <!-- Banner upload -->
        <label class="label">Баннер (необязательно)</label>
        <div
          class="drop-zone"
          :class="{ dragover: isDragover }"
          @drop.prevent="onDrop"
          @dragover.prevent="isDragover = true"
          @dragleave="isDragover = false"
          @click="$refs.photoInput.click()"
        >
          <template v-if="!photoPreview">
            <div class="drop-icon">🖼️</div>
            <div class="drop-text">Перетащите изображение или нажмите для выбора</div>
          </template>
          <template v-else>
            <img :src="photoPreview" class="drop-preview" alt="Banner" />
            <button type="button" class="drop-remove" @click.stop="removePhoto">✕</button>
          </template>
        </div>
        <input
          ref="photoInput"
          type="file"
          accept="image/*"
          class="hidden"
          @change="onPhotoSelect"
        />

        <!-- CTA button -->
        <label class="label">Кнопка (необязательно)</label>
        <div class="btn-row">
          <input v-model="buttonText" class="input" placeholder="Текст кнопки" />
          <input v-model="buttonUrl" class="input" placeholder="https://example.com" />
        </div>

        <!-- Live preview -->
        <div class="preview-section">
          <label class="label">Предпросмотр</label>
          <div class="preview-card">
            <img v-if="photoPreview" :src="photoPreview" class="preview-banner" alt="" />
            <div v-if="message.trim()" class="preview-body" v-html="sanitizedPreview"></div>
            <div v-if="buttonText && buttonUrl" class="preview-button">
              {{ buttonText }}
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
import { ref, computed } from 'vue'
import { api } from '../api'

const message = ref('')
const textareaRef = ref(null)
const photoFile = ref(null)
const photoPreview = ref('')
const isDragover = ref(false)
const buttonText = ref('')
const buttonUrl = ref('')
const showEmoji = ref(false)
const showCustomEmoji = ref(false)
const customEmojiId = ref('')
const customEmojiAlt = ref('')
const activeEmojiCat = ref('smileys')
const error = ref('')
const result = ref('')
const loading = ref(false)

const emojiCategories = [
  { name: 'smileys', icon: '😀', items: ['😀','😃','😄','😁','😆','😅','🤣','😂','🙂','😊','😇','🥰','😍','🤩','😘','😗','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🫢','🤫','🤔','🫡','🤐','🤨','😐','😑','😶','🫥','😏','😒','🙄','😬','😮‍💨','🤥','😌','😔','😪','🤤','😴','😷','🤒','🤕','🤢','🤮','🥵','🥶','🥴','😵','🤯','🤠','🥳','🥸','😎','🤓','🧐','😕','🫤','😟','🙁','😮','😯','😲','😳','🥺','🥹','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','🥱','😤','😡','😠','🤬','😈','👿','💀','☠️','💩','🤡','👹','👺','👻','👽','👾','🤖'] },
  { name: 'hearts', icon: '❤️', items: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❤️‍🔥','❤️‍🩹','❣️','💕','💞','💓','💗','💖','💘','💝','💟','♥️','🫶','💑','💏','💋','😻','😽'] },
  { name: 'hands', icon: '👋', items: ['👋','🤚','🖐️','✋','🖖','🫱','🫲','🫳','🫴','👌','🤌','🤏','✌️','🤞','🫰','🤟','🤘','🤙','👈','👉','👆','🖕','👇','☝️','🫵','👍','👎','✊','👊','🤛','🤜','👏','🙌','🫶','👐','🤲','🤝','🙏','✍️','💪','🦾','🦿'] },
  { name: 'animals', icon: '🐱', items: ['🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐻‍❄️','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🙈','🙉','🙊','🐔','🐧','🐦','🐤','🦆','🦅','🦉','🦇','🐺','🐗','🐴','🦄','🐝','🪱','🐛','🦋','🐌','🐞','🐜','🪲','🪳','🕷️','🦂','🐢','🐍','🦎','🦖','🐙','🦑','🦐','🦞','🦀','🐡','🐠','🐟','🐬','🐳','🐋'] },
  { name: 'food', icon: '🍕', items: ['🍏','🍎','🍐','🍊','🍋','🍌','🍉','🍇','🍓','🫐','🍈','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🥑','🍆','🌶️','🫑','🥒','🥬','🥦','🧅','🧄','🥔','🍠','🥐','🥯','🍞','🥖','🧀','🥚','🍳','🥞','🧇','🥓','🥩','🍗','🍖','🦴','🌭','🍔','🍟','🍕','🫓','🥪','🌮','🌯','🫔','🥙','🧆','🥘','🍝','🍜'] },
  { name: 'objects', icon: '💡', items: ['⌚','📱','💻','⌨️','🖥️','🖨️','🖱️','🖲️','💾','💿','📀','📷','📹','🎥','📽️','🎬','📺','📻','🎙️','🎧','🔔','🔕','📢','📣','⏰','⏱️','⏲️','🕰️','💡','🔦','🕯️','💰','💳','💎','⚖️','🔧','🔨','⚒️','🛠️','⛏️','🔩','⚙️','🧲','🔫','💣','🧨','🪓','🔪','🗡️','⚔️','🛡️','🚬','⚰️','🏺','🔮','📿','🧿','💈','⚗️','🔭','🔬','🕳️'] },
  { name: 'symbols', icon: '✅', items: ['✅','❌','❓','❗','‼️','⁉️','💯','🔥','✨','⭐','🌟','💫','💥','💢','💦','💨','🕐','🔴','🟠','🟡','🟢','🔵','🟣','⚫','⚪','🟤','🔶','🔷','🔸','🔹','🔺','🔻','💠','🔘','🔳','🔲','🏁','🚩','🎌','🏴','🏳️','🏳️‍🌈','☑️','✔️','➕','➖','➗','✖️','♾️','💲','💱','©️','®️','™️','#️⃣','*️⃣','0️⃣','1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟'] },
]

const currentEmojis = computed(() => {
  const cat = emojiCategories.find(c => c.name === activeEmojiCat.value)
  return cat ? cat.items : []
})

const sanitizedPreview = computed(() => {
  // Allow only Telegram-supported HTML tags for preview
  let html = message.value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // Restore allowed tags
  const tags = ['b', 'i', 'u', 's', 'code', 'pre', 'a', 'tg-emoji']
  for (const tag of tags) {
    // opening tags with attributes
    html = html.replace(new RegExp(`&lt;(${tag})(\\s[^&]*?)?&gt;`, 'gi'), '<$1$2>')
    // closing tags
    html = html.replace(new RegExp(`&lt;/${tag}&gt;`, 'gi'), `</${tag}>`)
  }
  return html
})

function wrapTag(tag) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const text = message.value
  const selected = text.substring(start, end)
  const wrapped = `<${tag}>${selected}</${tag}>`
  message.value = text.substring(0, start) + wrapped + text.substring(end)
  // Restore cursor
  const cursorPos = start + tag.length + 2 + selected.length + tag.length + 3
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(cursorPos, cursorPos)
  })
}

function insertLink() {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const text = message.value
  const selected = text.substring(start, end) || 'текст ссылки'
  const url = prompt('Введите URL:', 'https://')
  if (!url) return
  const link = `<a href="${url}">${selected}</a>`
  message.value = text.substring(0, start) + link + text.substring(end)
}

function insertEmoji(em) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const text = message.value
  message.value = text.substring(0, start) + em + text.substring(start)
  const pos = start + em.length
  requestAnimationFrame(() => {
    ta.focus()
    ta.setSelectionRange(pos, pos)
  })
}

function insertCustomEmoji() {
  if (!customEmojiId.value.trim()) return
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const text = message.value
  const alt = customEmojiAlt.value.trim() || '⭐'
  const tag = `<tg-emoji emoji-id="${customEmojiId.value.trim()}">${alt}</tg-emoji>`
  message.value = text.substring(0, start) + tag + text.substring(start)
  customEmojiId.value = ''
  customEmojiAlt.value = ''
}

function onPhotoSelect(e) {
  const file = e.target.files?.[0]
  if (file && file.type.startsWith('image/')) {
    setPhoto(file)
  }
}

function onDrop(e) {
  isDragover.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    setPhoto(file)
  }
}

function setPhoto(file) {
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value)
  photoFile.value = file
  photoPreview.value = URL.createObjectURL(file)
}

function removePhoto() {
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value)
  photoFile.value = null
  photoPreview.value = ''
}

async function submit() {
  error.value = ''
  result.value = ''
  const text = message.value.trim()

  if (!text && !photoFile.value) {
    error.value = 'Введите текст и/или приложите изображение'
    return
  }

  if (photoFile.value && text.length > 1024) {
    error.value = `Текст с фото не должен превышать 1024 символа (сейчас: ${text.length})`
    return
  }

  if (!confirm('Отправить рекламный пост всем подписчикам?')) return

  loading.value = true
  try {
    const form = new FormData()
    form.append('message', text)
    if (photoFile.value) form.append('photo', photoFile.value)
    if (buttonText.value.trim() && buttonUrl.value.trim()) {
      form.append('button_text', buttonText.value.trim())
      form.append('button_url', buttonUrl.value.trim())
    }
    const data = await api.sendAd(form)
    result.value = `Разослано: ${data.sent}, ошибок: ${data.failed}.`
    message.value = ''
    removePhoto()
    buttonText.value = ''
    buttonUrl.value = ''
  } catch (e) {
    error.value = e.message || 'Ошибка отправки'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.ads { display: flex; flex-direction: column; gap: 1rem; }
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
.label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; margin-top: 1rem; }
.label:first-child { margin-top: 0; }

/* Toolbar */
.toolbar {
  display: flex;
  gap: 4px;
  margin-bottom: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.tb-btn {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  padding: 6px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  line-height: 1;
}
.tb-btn:hover { border-color: var(--accent); }
.tb-btn.active { background: var(--accent); color: var(--bg); }
.tb-sep { width: 1px; height: 24px; background: var(--border); margin: 0 4px; }

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
}
.textarea:focus { border-color: var(--accent); }
.char-count { font-size: 0.75rem; color: var(--text-muted); text-align: right; margin-bottom: 0.5rem; }
.char-count.warn { color: var(--danger); }

/* Emoji picker */
.emoji-panel {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
}
.emoji-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.emoji-tab {
  font-size: 1.2rem;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.emoji-tab:hover { border-color: var(--border); }
.emoji-tab.active { border-color: var(--accent); background: var(--bg-card); }
.emoji-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  max-height: 200px;
  overflow-y: auto;
}
.emoji-item {
  font-size: 1.3rem;
  padding: 4px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  line-height: 1;
}
.emoji-item:hover { background: var(--border); }

/* Custom emoji */
.custom-emoji-panel {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
}
.custom-emoji-panel .label { margin-top: 0; }
.custom-emoji-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.input {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  outline: none;
  flex: 1;
}
.input:focus { border-color: var(--accent); }
.input--small { max-width: 120px; flex: 0 0 auto; }

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--border);
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  position: relative;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.drop-zone:hover, .drop-zone.dragover {
  border-color: var(--accent);
  background: rgba(0, 212, 170, 0.05);
}
.drop-icon { font-size: 2rem; margin-bottom: 0.5rem; }
.drop-text { font-size: 0.85rem; color: var(--text-muted); }
.drop-preview {
  max-width: 100%;
  max-height: 300px;
  border-radius: 6px;
  object-fit: contain;
}
.drop-remove {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--danger);
  color: #fff;
  border: none;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.hidden { display: none; }

/* CTA button fields */
.btn-row {
  display: flex;
  gap: 8px;
}

/* Preview */
.preview-section { margin-top: 1rem; }
.preview-card {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.preview-banner {
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  display: block;
}
.preview-body {
  padding: 0.75rem 1rem;
  font-size: 0.95rem;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.preview-body :deep(a) { color: var(--accent); text-decoration: underline; }
.preview-button {
  margin: 0.5rem 1rem 1rem;
  padding: 0.6rem 1rem;
  background: rgba(0, 212, 170, 0.15);
  border: 1px solid var(--accent);
  border-radius: 8px;
  color: var(--accent);
  text-align: center;
  font-size: 0.9rem;
}

.error { font-size: 0.9rem; color: var(--danger); margin-top: 0.75rem; }
.result { font-size: 0.9rem; color: var(--accent); margin-top: 0.75rem; }

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
  margin-top: 1rem;
}
.btn:hover:not(:disabled) { background: var(--accent-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn--sm {
  font-size: 0.8rem;
  padding: 0.5rem 0.75rem;
  margin-top: 0;
  flex-shrink: 0;
}
</style>
