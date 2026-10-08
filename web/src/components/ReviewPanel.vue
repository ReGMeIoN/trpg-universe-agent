<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ status: Object })

const groups = ref([])
const group = ref('')
const items = ref([])
const decisions = ref([])       // 本地裁决草稿
const decisionsFile = ref('')
const err = ref('')
const msg = ref('')
const busy = ref(false)

const targets = ['characters', 'character_updates', 'relations', 'players', 'pl_profiles', 'pending']

async function loadGroups() {
  try {
    const gs = await api.groups()
    groups.value = gs.filter((g) => g.pending > 0 || g.has_patch)
    if (!group.value && groups.value.length) group.value = groups.value[0].group
  } catch (e) {
    err.value = String(e.message || e)
  }
}
loadGroups()

async function load() {
  if (!group.value) return
  try {
    const r = await api.review(group.value)
    items.value = r.items
    decisionsFile.value = r.decisions_file
    decisions.value = (r.decisions || []).filter((d) => d.target && d.index !== undefined && d.index !== null)
      .map((d) => ({ ...d }))
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}
watch(group, load)

function key(it) { return `${it.target}:${it.index}` }
function decided(it) { return decisions.value.find((d) => d.target === it.target && d.index === it.index) }

function setAction(it, action, extra = {}) {
  const idx = decisions.value.findIndex((d) => d.target === it.target && d.index === it.index)
  const d = { target: it.target, index: it.index, action, ...extra }
  if (idx >= 0) decisions.value.splice(idx, 1, d)
  else decisions.value.push(d)
}

function unset(it) {
  const idx = decisions.value.findIndex((d) => d.target === it.target && d.index === it.index)
  if (idx >= 0) decisions.value.splice(idx, 1)
}

async function save() {
  busy.value = true
  try {
    const r = await api.saveDecisions(group.value, decisions.value)
    msg.value = `已保存 ${r.saved} 条裁决 -> ${r.file}`
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function apply() {
  if (!confirm('把裁决写回补丁与称呼表？（不写数据目录，之后仍需 store）')) return
  busy.value = true
  try {
    await api.saveDecisions(group.value, decisions.value)
    const r = await api.applyDecisions(group.value)
    msg.value = `已应用：补丁改动 ${r.applied.length} 项，称呼归一 ${r.naming_merges.length} 项`
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

function setField(it) {
  const field = prompt('要改哪个字段？（如 played_by / name / note）')
  if (!field) return
  const value = prompt(`把 ${field} 改成：`)
  if (value === null) return
  setAction(it, 'set', { field, value })
}

function mergeNaming(it) {
  const canonical = prompt('归一到哪个标准称呼？（如 菌羊）')
  if (!canonical) return
  const variant = prompt('被归一的写法是？（如 军羊）')
  if (!variant) return
  decisions.value.push({ action: 'merge', canonical, variant })
}

const progress = computed(() => `${decisions.value.length} / ${items.value.length}`)
</script>

<template>
  <div class="card">
    <h2>待确认裁决</h2>
    <div class="row">
      <select v-model="group" style="min-width:320px">
        <option v-for="g in groups" :key="g.group" :value="g.group">
          {{ g.group }} · 待确认 {{ g.pending }}
        </option>
      </select>
      <button class="act" @click="load">重新载入</button>
      <span class="spacer"></span>
      <span class="badge">{{ progress }} 已裁决</span>
      <button class="act" :disabled="busy || !decisions.length" @click="save">保存裁决</button>
      <button class="act primary" :disabled="busy || !decisions.length" @click="apply">保存并应用</button>
    </div>
    <div class="muted" style="margin-top:8px">
      裁决写回<b>补丁与称呼表</b>（不写数据目录）。之后到「启动任务」跑 <code>store</code> 出工作副本，确认无误再回填。
      <span v-if="decisionsFile">文件：<code>{{ decisionsFile }}</code></span>
    </div>
    <div class="err" v-if="err">{{ err }}</div>
    <div class="muted" v-if="msg" style="color:var(--ok)">{{ msg }}</div>
  </div>

  <div class="card" v-for="it in items" :key="key(it)">
    <div class="row">
      <span class="seg">({{ it.target }}[{{ it.index }}])</span>
      <span v-if="it.segment" class="badge">{{ it.segment }}</span>
      <span class="spacer"></span>
      <span class="badge" :class="decided(it) ? 'ok' : ''" v-if="decided(it)">
        {{ decided(it).action }}{{ decided(it).value !== undefined ? ` → ${decided(it).value}` : '' }}
      </span>
      <button class="act" @click="setAction(it, 'accept')">确认入库</button>
      <button class="act" @click="setAction(it, 'reject')">驳回</button>
      <button class="act" @click="setField(it)">改字段</button>
      <button class="act" @click="mergeNaming(it)">并入称呼表</button>
      <button class="act" v-if="decided(it)" @click="unset(it)">撤销</button>
    </div>
    <div style="margin-top:6px;font-weight:600">{{ it.summary }}</div>
    <div class="muted" v-if="it.reason">{{ it.reason }}</div>
  </div>

  <div class="card" v-if="!items.length && group">
    <div class="muted">该团没有待确认项（或还没有补丁）。</div>
  </div>
</template>
