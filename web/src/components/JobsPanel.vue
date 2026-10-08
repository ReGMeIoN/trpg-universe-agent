<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '../api'

const props = defineProps({ status: Object })

const jobs = ref([])
const sel = ref(null)
const log = ref('')
const err = ref('')
const autoScroll = ref(true)
const tail = ref(200)
let timer = null

const selected = computed(() => jobs.value.find((x) => x.id === sel.value) || null)

async function load() {
  try {
    jobs.value = await api.jobs()
    if (!sel.value && jobs.value.length) sel.value = jobs.value[0].id
    if (sel.value) {
      const r = await api.jobLog(sel.value, tail.value)
      log.value = r.log
    }
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function badge(s) {
  if (s === 'finished') return 'ok'
  if (s === 'running') return 'run'
  if (s === 'failed' || s === 'killed') return 'err'
  return ''
}

function pct(j) {
  const p = j.extra?.progress?.percent
  return p === null || p === undefined ? null : p
}

async function kill(id) {
  if (!confirm('确认中断该任务？断点已保存，之后可续跑。')) return
  try {
    await api.jobKill(id)
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function fmt(ts) {
  return ts ? String(ts).slice(5) : '-'
}

onMounted(() => {
  load()
  timer = setInterval(load, 2000)
})
onUnmounted(() => timer && clearInterval(timer))
</script>

<template>
  <div class="err" v-if="err">{{ err }}</div>

  <div class="card">
    <h2>任务列表（每 2 秒自动刷新）</h2>
    <table>
      <thead>
        <tr>
          <th>任务</th><th>类型</th><th>状态</th><th style="width:22%">进度</th>
          <th>启动</th><th>pid</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="j in jobs" :key="j.id" @click="sel = j.id" style="cursor:pointer"
            :style="sel === j.id ? 'background:#eef6f5' : ''">
          <td style="font-family:Consolas,monospace;font-size:12px">
            {{ j.id }}
            <div class="seg" v-if="j.extra?.group">团：{{ j.extra.group }}</div>
          </td>
          <td>{{ j.kind }}</td>
          <td><span class="badge" :class="badge(j.status)">{{ j.status }}</span></td>
          <td>
            <div v-if="pct(j) !== null">
              <div style="background:#eee;border-radius:6px;height:8px;overflow:hidden">
                <div :style="{ width: pct(j) + '%', height: '8px', background: 'var(--brand)' }"></div>
              </div>
              <span class="seg">{{ pct(j) }}%
                <template v-if="j.extra?.progress?.segments">· {{ j.extra.progress.segments }} 段</template>
              </span>
            </div>
            <span class="muted" v-else>—</span>
          </td>
          <td class="seg">{{ fmt(j.started) }}</td>
          <td class="seg">{{ j.pid }}</td>
          <td>
            <button class="act danger" v-if="j.status === 'running'" @click.stop="kill(j.id)">中断</button>
            <span class="muted" v-else>—</span>
          </td>
        </tr>
        <tr v-if="!jobs.length"><td colspan="7" class="muted">暂无任务</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card" v-if="selected">
    <h2>日志 · {{ selected.id }}</h2>
    <div class="row" style="margin-bottom:8px">
      <label><input type="checkbox" v-model="autoScroll"> 跟随滚动</label>
      <label>显示行数 <input type="number" v-model.number="tail" style="width:90px" @change="load"></label>
      <span class="muted">共 {{ log.split('\n').length }} 行</span>
    </div>
    <div class="pre" :key="selected.id" ref="box">{{ log || '（无日志）' }}</div>
  </div>
</template>
