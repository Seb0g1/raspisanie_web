const API = '/api'

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData
  const res = await fetch(API + path, {
    ...options,
    headers: isFormData ? { ...options.headers } : {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || res.statusText)
  return data
}

export const api = {
  me: () => request('/me'),
  login: (password) => request('/login', { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request('/logout', { method: 'POST' }),
  stats: () => request('/stats'),
  broadcast: (message) => request('/broadcast', { method: 'POST', body: JSON.stringify({ message }) }),
  broadcastWithFiles: (formData) => request('/broadcast', { method: 'POST', body: formData }),
  feedback: () => request('/feedback'),
  feedbackReply: (id, reply) => request(`/feedback/${id}/reply`, { method: 'POST', body: JSON.stringify({ reply }) }),
  checkmail: () => request('/checkmail', { method: 'POST' }),
  uploadSchedule: (formData) => request('/upload-schedule', { method: 'POST', body: formData }),
  schedules: () => request('/schedules'),
  mailScan: () => request('/mail/scan'),
  mailProcess: (msg_id, notify) => request('/mail/process', { method: 'POST', body: JSON.stringify({ msg_id, notify }) }),
  sendAd: (formData) => request('/ads/send', { method: 'POST', body: formData }),
}
