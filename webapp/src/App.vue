<template>
  <div class="app">
    <header v-if="isLoggedIn" class="header">
      <router-link to="/" class="logo">Расписание</router-link>
      <nav class="nav">
        <router-link to="/">Главная</router-link>
        <router-link to="/users">Пользователи</router-link>
        <router-link to="/broadcast">Рассылка</router-link>
        <router-link to="/feedback">Обратная связь</router-link>
        <router-link to="/upload">Загрузить</router-link>
        <router-link to="/ads">Реклама</router-link>
        <button type="button" class="btn-logout" @click="logout">Выход</button>
      </nav>
    </header>
    <main class="main" :class="{ 'main--full': !isLoggedIn }">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from './api'

const router = useRouter()
const route = useRoute()

const isLoggedIn = computed(() => route.name !== 'Login')

async function logout() {
  try {
    await api.logout()
    router.push({ name: 'Login' })
  } catch (_) {}
}
</script>

<style>
:root {
  --bg: #0c0c0f;
  --bg-card: #14141a;
  --bg-input: #1a1a22;
  --border: #2a2a35;
  --text: #e8e8ed;
  --text-muted: #8888a0;
  --accent: #00d4aa;
  --accent-hover: #00f0c0;
  --danger: #ff4757;
  --radius: 12px;
  --font-sans: 'Unbounded', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; }
body {
  font-family: var(--font-mono);
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  line-height: 1.5;
}
.app { min-height: 100vh; display: flex; flex-direction: column; }
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.logo {
  font-family: var(--font-sans);
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--accent);
  text-decoration: none;
  letter-spacing: 0;
}
.nav {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}
.nav a {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 0.875rem;
  transition: color 0.2s;
}
.nav a:hover, .nav a.router-link-active { color: var(--accent); }
.btn-logout {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.btn-logout:hover { border-color: var(--danger); color: var(--danger); }
.main {
  flex: 1;
  padding: 1.5rem;
  max-width: 1120px;
  margin: 0 auto;
  width: 100%;
}
.main--full { max-width: 440px; padding-top: 3rem; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (max-width: 760px) {
  .header { align-items: flex-start; flex-direction: column; }
  .nav { justify-content: flex-start; gap: 0.75rem; }
  .main { padding: 1rem; }
}
</style>
