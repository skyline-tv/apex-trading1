import axios from 'axios'

const apiToken = (import.meta.env.VITE_API_TOKEN || '').trim()
const configuredApiUrl = (import.meta.env.VITE_API_URL || '').trim()
const fallbackApiUrl = import.meta.env.DEV ? 'http://localhost:8000' : ''

export const API_BASE_URL = configuredApiUrl || fallbackApiUrl

const api = axios.create({
  baseURL: API_BASE_URL || undefined,
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  if (apiToken) {
    config.headers = config.headers || {}
    config.headers['x-api-key'] = apiToken
  }
  return config
})

export const runTrade = (asset) =>
  api.post(`/run${asset ? `?asset=${asset}` : ''}`)

export const getPortfolio = () => api.get('/portfolio')
export const getQuotes = (assets = []) =>
  api.get(`/quotes${assets.length ? `?assets=${encodeURIComponent(assets.join(','))}` : ''}`)

export const getHistory = (limit = 50, options = {}) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (options.closedOnly) params.set('closed_only', 'true')
  return api.get(`/history?${params.toString()}`)
}
export const getRuleLogs = (limit = 100) => api.get(`/rule-logs?limit=${limit}`)
export const getPerformanceReport = (limit = 1000) =>
  api.get(`/performance/report?limit=${limit}`)

export const getSettings = () => api.get('/settings')

export const saveSettings = (data) => api.patch('/settings', data)

export const resetWallet = () => api.post('/reset?confirm=true')

export const getAutoTradeStatus = () => api.get('/autotrade/status')
export const startAutoTrade = () => api.post('/autotrade/start')
export const stopAutoTrade = () => api.post('/autotrade/stop')

export default api
