<script setup>
import { ref, computed } from 'vue'
import { api } from '../api'

const props = defineProps({ ws: Object, status: Object })
const emit = defineEmits(['started'])

const groups = ref([])
const err = ref('')
const busy = ref(false)

// 启动任务表单
const form = ref({
  step: 'extract',
  group: '',
  apply: false,
  allow_production: false,
  force: false,
  smoke: 0,
  all_groups: false,
})

const steps = ['ingest', 'transcribe', 'segment', 'extract', 'store', 'visualize', 'export', 'housekeep']
const counts = computed(() => props.status?.counts || {})
const stepRows = computed(() => Object.entries(props.status?.steps || {}))
const dirty = computed(() => props.status?.data_hygiene?.dirty_group_values || {})
const manifest = computed(() => props.status?.manifest || {})

async function load() {
  try {
    groups.value = await api.groups()
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}
load()

function statusBadge(s) {
  if (s === 'done') return 'ok'
  if (s === 'running') return 'run'
  if (s === 'failed') return 'err'
  return ''
}

async function start() {
  if (form.value.step === 'store' && form.value.apply && props.ws?.is_production && !form.value.allow_production) {
    err.value = '生产库回填必须同时勾选「允许写生产库」'
    return
  }
  busy.value = true
  try {
    const body = { ...form.value }
    if (!body.group) delete body.group
    if (!body.smoke) delete body.smoke
    const rec = await api.startJob(body)
    err.value = ''
    emit('started', rec.id)
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function quick(step, group) {
  busy.value = true
  try {
    await api.startJob({ step, group })
    emit('started')
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid cols-4">
    <div class="stat"><div class="n">{{ counts.characters ?? '-' }}</div><div class="l">角色</div></div>
    <div class="stat"><div class="n">{{ counts.relations ?? '-' }}</div><div class="l">关系</div></div>
    <div class="stat"><div class="n">{{ counts.players ?? '-' }}</div><div class="l">玩家</div></div>
    <div class="stat"><div class="n">{{ counts.pl_profiles ?? '-' }}</div><div class="l">PL 画像</div></div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>启动任务</h2>
    <div class="row">
      <select v-model="form.step">
        <option v-for="s in steps" :key="s" :value="s">{{ s }}</option>
      </select>
      <select v-model="form.group">
        <option value="">（该步骤默认范围）</option>
        <option v-for="g in groups" :key="g.group" :value="g.group">
          {{ g.group }} · {{ g.segments }}段
        </option>
      </select>
      <label v-if="form.step === 'transcribe'"><input type="checkbox" v-model="form.force"> 重跑</label>
      <label v-if="form.step === 'transcribe'">冒烟秒数 <input type="number" v-model.number="form.smoke" style="width:80px"></label>
      <label v-if="form.step === 'extract'"><input type="checkbox" v-model="form.force"> 重跑已有提炼</label>
      <label v-if="form.step === 'visualize'"><input type="checkbox" v-model="form.all_groups"> 所有团</label>
      <label v-if="form.step === 'store'"><input type="checkbox" v-model="form.apply"> 回填数据(先备份)</label>
      <label v-if="form.step === 'store' && form.apply">
        <input type="checkbox" v-model="form.allow_production"> 允许写生产库
      </label>
      <button class="act primary" :disabled="busy" @click="start">启动</button>
    </div>
    <div class="muted" style="margin-top:8px">
      任务在后台独立进程运行（脱离本页面），可在「任务与进度」实时跟踪；关掉页面也不会中断。
    </div>
    <div class="err" v-if="err">{{ err }}</div>
  </div>

  <div class="card">
    <h2>流程状态</h2>
    <div class="row" style="gap:16px">
      <span v-for="[k, v] in stepRows" :key="k">
        <span class="badge" :class="statusBadge(v.status)">{{ k }} {{ v.status }}</span>
      </span>
    </div>
    <div class="muted" style="margin-top:8px">
      素材 {{ manifest.counts?.total ?? '-' }} 个文件 · 团 {{ (manifest.groups || []).length }} 个
      <template v-if="manifest.superseded_groups?.length">
        · 已停用 {{ manifest.superseded_groups.join('、') }}
      </template>
    </div>
  </div>

  <div class="card" v-if="Object.keys(dirty).length">
    <h2>数据卫生提醒</h2>
    <div class="muted">
      <b>{{ Object.keys(dirty).join('、') }}</b> 被写进了 <code>groups</code> 字段（应只在 <code>tags</code> 里）。
      涉及 {{ Object.values(dirty).flat().length }} 个角色：
      {{ Object.values(dirty).flat().join('、') }}
    </div>
    <div class="muted">已由 <code>data_utils</code> 守卫，不会凭空虚构成团；是否修正数据需人工决定。</div>
  </div>

  <div class="card">
    <h2>团清单</h2>
    <table>
      <thead>
        <tr>
          <th>团</th><th class="num">角色</th><th class="num">段</th><th class="num">提炼</th>
          <th>补丁</th><th>报告</th><th class="num">待确认</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.group">
          <td>{{ g.group }}</td>
          <td class="num">{{ g.characters }}</td>
          <td class="num">{{ g.segments }}</td>
          <td class="num">{{ g.extracts }}</td>
          <td><span class="badge" :class="g.has_patch ? 'ok' : ''">{{ g.has_patch ? '有' : '无' }}</span></td>
          <td><span class="badge" :class="g.has_report ? 'ok' : ''">{{ g.has_report ? '有' : '无' }}</span></td>
          <td class="num">{{ g.pending }}</td>
          <td>
            <div class="row" style="gap:4px">
              <button class="act" :disabled="busy || !g.segments" @click="quick('extract', g.group)">提炼</button>
              <button class="act" :disabled="busy || !g.has_patch" @click="quick('store', g.group)">入库副本</button>
              <button class="act" :disabled="busy" @click="quick('visualize', g.group)">出图</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <div class="muted" style="margin-top:8px">
      「入库副本」只写工作副本与报告，不动数据目录；确认无误后再用命令加 <code>--apply --allow-production</code> 回填。
    </div>
  </div>
</template>
