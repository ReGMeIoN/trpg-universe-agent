<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import { api, productUrl } from '../api'

const products = ref([])
const sel = ref(null)
const md = ref('')
const err = ref('')
const filter = ref('')
const loading = ref(false)

async function load() {
  try {
    products.value = await api.products()
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}
load()

const shown = computed(() => {
  const k = filter.value.trim()
  if (!k) return products.value
  return products.value.filter((p) => p.path.includes(k))
})

function isHtml(p) { return p && p.suffix === '.html' }

async function open(p) {
  sel.value = p
  md.value = ''
  if (isHtml(p)) return
  loading.value = true
  try {
    const r = await api.markdownProduct(p.path)
    md.value = marked.parse(r.markdown || '')
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    loading.value = false
  }
}

function kb(n) {
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}
</script>

<template>
  <div class="err" v-if="err">{{ err }}</div>

  <div class="card">
    <h2>产物预览（{{ products.length }} 个文件）</h2>
    <div class="row" style="margin-bottom:10px">
      <input v-model="filter" placeholder="过滤文件名，如 关系图 / 编年史 / 总览" style="min-width:280px" />
      <span class="muted">HTML 关系图直接内嵌渲染；Markdown 渲染为可读文档</span>
    </div>
    <table>
      <thead><tr><th>文件</th><th class="num">大小</th><th></th></tr></thead>
      <tbody>
        <tr v-for="p in shown" :key="p.path">
          <td>
            <a href="#" @click.prevent="open(p)">{{ p.name }}</a>
            <div class="seg">{{ p.path }}</div>
          </td>
          <td class="num">{{ kb(p.size) }}</td>
          <td class="seg">{{ p.suffix }}</td>
        </tr>
        <tr v-if="!shown.length"><td colspan="3" class="muted">没有产物；先跑 visualize / export</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card" v-if="sel">
    <div class="row">
      <h2 style="margin:0">{{ sel.name }}</h2>
      <span class="spacer"></span>
      <a :href="productUrl(sel.path)" target="_blank" class="muted">新标签打开</a>
    </div>
    <div style="margin-top:10px">
      <iframe v-if="isHtml(sel)" class="view" :src="productUrl(sel.path)" />
      <div v-else class="md" v-html="md"></div>
      <div class="muted" v-if="loading">渲染中…</div>
    </div>
  </div>
</template>
