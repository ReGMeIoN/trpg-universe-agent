<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from './api'
import Overview from './components/Overview.vue'
import JobsPanel from './components/JobsPanel.vue'
import ReviewPanel from './components/ReviewPanel.vue'
import ProductsPanel from './components/ProductsPanel.vue'

const tab = ref('overview')
const ws = ref(null)
const status = ref(null)
const error = ref('')
const tabs = [
  { k: 'overview', label: '概览' },
  { k: 'jobs', label: '任务与进度' },
  { k: 'review', label: '待确认裁决' },
  { k: 'products', label: '产物预览' },
]

async function refresh() {
  try {
    ws.value = await api.workspace()
    status.value = await api.status()
    error.value = ''
  } catch (e) {
    error.value = String(e.message || e)
  }
}

let timer = null
onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})
onUnmounted(() => timer && clearInterval(timer))

function onStarted() {
  tab.value = 'jobs'
  refresh()
}
</script>

<template>
  <div class="topbar">
    <h1>🐳 TRPG-Universe Agent</h1>
    <span class="path" v-if="ws">{{ ws.root }}</span>
    <span class="badge prod" v-if="ws && ws.is_production">生产库</span>
    <span class="badge" v-if="ws && ws.writable === false">只读模式</span>
    <span class="badge" v-if="status && status.llm">
      LLM: {{ status.llm.routes.extract }} → {{ status.llm.providers[status.llm.routes.extract]?.model }}
    </span>
    <span class="spacer"></span>
    <span class="err" v-if="error">{{ error }}</span>
    <button class="act" @click="refresh">刷新</button>
    <a class="act" href="/docs" target="_blank" style="text-decoration:none">API 文档</a>
  </div>

  <div class="tabs">
    <button v-for="t in tabs" :key="t.k" :class="{ active: tab === t.k }" @click="tab = t.k">
      {{ t.label }}
    </button>
  </div>

  <div class="page">
    <Overview v-if="tab === 'overview'" :ws="ws" :status="status" @started="onStarted" />
    <JobsPanel v-else-if="tab === 'jobs'" :status="status" />
    <ReviewPanel v-else-if="tab === 'review'" :status="status" />
    <ProductsPanel v-else-if="tab === 'products'" />
  </div>
</template>
