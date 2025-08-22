<template>
  <UContainer class="py-6 space-y-6">
    <!-- Top controls -->
    <div class="max-w-5xl mx-auto flex flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <UButton color="warning" variant="soft" @click="armAllJointsArmAllPost()">Arm All</UButton>
          <UButton color="success" variant="soft" @click="disarmAllJointsDisarmAllPost()">Disarm All</UButton>
        </div>

        <div class="flex items-center gap-3">
          <USwitch v-model="recording" />
          <span class="text-sm text-gray-500">Record run</span>
          <span v-if="currentRunId" class="text-xs px-2 py-1 rounded bg-gray-100">run_id: {{ currentRunId }}</span>
          <UButton v-if="!currentRunId && recording" size="xs" @click="startRun">Start</UButton>
          <UButton v-if="currentRunId && recording" size="xs" color="error" variant="soft" @click="stopRun">Stop
          </UButton>
        </div>
      </div>
    </div>

    <!-- Joint Cards -->
    <div class="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
      <UCard v-for="joint in joints" :key="joint.id" class="overflow-hidden">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-lg">{{ joint.id }}</span>
              <UBadge :color="joint.type === 'odrive' ? 'primary' : 'secondary'">{{ joint.type }}</UBadge>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500">{{ joint.online ? 'online' : 'offline' }}</span>
              <span
                :class="['inline-block h-2.5 w-2.5 rounded-full', joint.online ? 'bg-emerald-500' : 'bg-gray-300']" />
            </div>
          </div>
        </template>

        <div class="space-y-4">
          <!-- Live telemetry quick stats -->
          <div class="grid grid-cols-3 gap-4 text-sm">
            <div class="p-3 rounded border bg-white">
              <div class="text-gray-500">Position</div>
              <div class="font-semibold">{{ formatNum(joint.last.position) }} turns</div>
            </div>
            <div class="p-3 rounded border bg-white">
              <div class="text-gray-500">Velocity</div>
              <div class="font-semibold">{{ formatNum(joint.last.velocity) }} rev/s</div>
            </div>
            <div class="p-3 rounded border bg-white">
              <div class="text-gray-500">Supply</div>
              <div class="font-semibold">{{ formatNum(joint.last.supply_v) }} V</div>
            </div>
          </div>

          <!-- Sparklines -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="flex items-center justify-between mb-2 text-xs text-gray-500">
                <span>Position (10s)</span>
                <span v-if="joint.live.length">{{ formatNum(joint.live[joint.live.length - 1]?.position) }} turns</span>
              </div>
              <SparkLine :points="joint.live" y-key="position" />
            </div>
            <div>
              <div class="flex items-center justify-between mb-2 text-xs text-gray-500">
                <span>Velocity (10s)</span>
                <span v-if="joint.live.length">{{ formatNum(joint.live[joint.live.length - 1]?.velocity) }} rev/s</span>
              </div>
              <SparkLine :points="joint.live" y-key="velocity" />
            </div>
          </div>

          <!-- Command controls -->
          <div class="flex flex-col gap-4">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
              <UFormField label="Position (turns)">
                <UInput v-model.number="joint.cmd.position" type="number" step="0.001" />
              </UFormField>
              <UFormField label="Velocity (rev/s)">
                <UInput v-model.number="joint.cmd.velocity" type="number" step="0.01" placeholder="auto" />
              </UFormField>
              <UFormField label="Accel (rev/s²)">
                <UInput v-model.number="joint.cmd.accel" type="number" step="0.01" placeholder="auto" />
              </UFormField>
              <UFormField label="Hold">
                <div class="h-10 flex items-center">
                  <UCheckbox v-model="joint.cmd.hold" />
                </div>
              </UFormField>
            </div>

            <div class="flex items-center gap-3">
              <UButton :disabled="!joint.online || sending[joint.id]" @click="sendMove(joint)">
                <UIcon name="i-heroicons-play" class="mr-1" /> Move
              </UButton>
              <UButton variant="outline" color="neutral" :disabled="sending[joint.id]" @click="stopJointJointsJointNameStopPost({ path: { joint_name: joint.id } })">
                <UIcon name="i-heroicons-stop" class="mr-1" /> Stop
              </UButton>
              <UButton variant="ghost" color="warning" @click="calibrateJointJointsJointNameCalibratePost({ path: { joint_name: joint.id } })">Calibrate</UButton>
              <UModal title="Configure Joint Values">
                <UButton variant="ghost" color="info" >Configure</UButton>

                <template #body>
                  <JointConfiguration :joint-name="joint.id" />
                </template>
              </UModal>
              <div class="text-xs text-gray-500 ml-auto" v-if="joint.lastCmd">
                last cmd: <span class="font-mono">{{ joint.lastCmd.cmd_id }}</span>
                <UBadge v-if="joint.lastCmd.accepted === false" color="error" class="ml-2">rejected</UBadge>
                <UBadge v-else-if="joint.lastCmd.done" color="success" class="ml-2">done</UBadge>
                <UBadge v-else color="info" class="ml-2">sent</UBadge>
              </div>
            </div>
          </div>
        </div>

        <template #footer>
          <div class="text-xs text-gray-400 flex items-center justify-between">
            <div>WS: <span
                :class="['inline-block h-2 w-2 rounded-full mr-1', joint.ws && joint.ws.readyState === 1 ? 'bg-emerald-500' : 'bg-gray-300']" />
              {{ wsLabel(joint.ws) }}</div>
            <div v-if="joint.last.ts">Last update: {{ new Date(joint.last.ts).toLocaleTimeString() }}</div>
          </div>
        </template>
      </UCard>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { client as apiClient } from '~/client/client.gen'
import {
  listJointsJointsIndexGet,
  moveJointJointsJointNameMovePost,
  stopJointJointsJointNameStopPost,
  calibrateJointJointsJointNameCalibratePost,
  armAllJointsArmAllPost,
  disarmAllJointsDisarmAllPost,
  startRun as startRunApi,
  stopRun as stopRunApi,
} from '~/client/sdk.gen'


apiClient.setConfig({ baseUrl: '/api' })

// --- Types ---
interface JointDto { id: string; type: 'odrive' | 'moteus'; initialized?: boolean }

interface LivePoint {
  ts: number
  position: number | null
  velocity: number | null
  supply_v?: number | null
}

interface JointState {
  id: string
  type: 'odrive' | 'moteus'
  online: boolean
  ws?: WebSocket | null
  live: LivePoint[]
  last: { ts: number | null; position: number | null; velocity: number | null; supply_v: number | null }
  cmd: { position: number | null; velocity?: number | null; accel?: number | null; hold: boolean }
  lastCmd: { cmd_id: string; accepted: boolean | null; done?: boolean } | null
}

// WebSocket message payloads (as emitted by your backend)
type TelemetryMsg = {
  type: 'telemetry'
  ts?: string
  position?: number
  velocity?: number
  supply_v?: number
}
type StatusMsg = { type: 'status'; online?: boolean }
type PingMsg = { type: 'ping' }
type CmdAckMsg = { type: 'cmd_ack'; cmd_id: string; accepted?: boolean }
type CmdDoneMsg = { type: 'cmd_done'; cmd_id: string }
type JointWsMsg = TelemetryMsg | StatusMsg | PingMsg | CmdAckMsg | CmdDoneMsg

// --- State ---
const joints = ref<JointState[]>([])
const sending = reactive<Record<string, boolean>>({})
const recording = ref(false)
const currentRunId = ref<number | null>(null)
const LIVE_MS = 10_000

// --- UI helpers ---
function formatNum(v: number | null | undefined, digits = 4) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return Number(v).toFixed(digits)
}
function wsLabel(ws?: WebSocket | null) {
  if (!ws) return 'disconnected'
  switch (ws.readyState) {
    case WebSocket.CONNECTING: return 'connecting'
    case WebSocket.OPEN: return 'open'
    case WebSocket.CLOSING: return 'closing'
    case WebSocket.CLOSED: return 'closed'
    default: return 'unknown'
  }
}

// --- Data loading ---
async function loadJoints() {
  const res = await listJointsJointsIndexGet()
  const list = (res?.data ?? []) as JointDto[]

  joints.value = list.map((j) => ({
    id: j.id,
    type: j.type,
    online: false,
    ws: null,
    live: [],
    last: { ts: null, position: null, velocity: null, supply_v: null },
    cmd: { position: 0, velocity: null, accel: null, hold: true },
    lastCmd: null,
  }))

  joints.value.forEach(openWs)
}

function openWs(joint: JointState) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.hostname}:8000/ws/joint/${joint.id}`
  const ws = new WebSocket(url)
  joint.ws = ws

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data) as JointWsMsg

    if (msg.type === 'telemetry') {
      joint.online = true
      const ts = msg.ts ? Date.parse(msg.ts) : Date.now()
      const p: LivePoint = {
        ts,
        position: msg.position ?? null,
        velocity: msg.velocity ?? null,
        supply_v: msg.supply_v ?? null,
      }
      joint.live.push(p)
      joint.last = { ts, position: p.position, velocity: p.velocity, supply_v: p.supply_v ?? null }
      const cutoff = Date.now() - LIVE_MS
      while (joint.live.length && joint.live[0].ts < cutoff) joint.live.shift()
      return
    }

    if (msg.type === 'status') {
      joint.online = !!msg.online
      return
    }

    if (msg.type === 'ping') {
      if (joint.ws && joint.ws.readyState === WebSocket.OPEN) joint.online = true
      return
    }

    if (msg.type === 'cmd_ack') {
      joint.lastCmd = { cmd_id: msg.cmd_id, accepted: !!msg.accepted }
      return
    }

    if (msg.type === 'cmd_done') {
      if (joint.lastCmd && joint.lastCmd.cmd_id === msg.cmd_id) joint.lastCmd.done = true
      return
    }
  }
  ws.onopen = () => { /* optimistic: status will arrive */ }
  ws.onclose = () => { joint.ws = null; joint.online = false; setTimeout(() => openWs(joint), 1500) }
}

// --- Commands ---
async function sendMove(j: JointState) {
  if (sending[j.id]) return
  sending[j.id] = true
  try {
    const r = (await moveJointJointsJointNameMovePost({
      path: { joint_name: j.id },
      query: {
      position: j.cmd.position,
      velocity: j.cmd.velocity ?? undefined,
      accel: j.cmd.accel ?? undefined,
      hold: j.cmd.hold,
      run_id: currentRunId.value ?? undefined,
    },
    }))

    const cmdId = r.data?.cmd_id
    if (cmdId) {
      j.lastCmd = { cmd_id: cmdId, accepted: true }
    }
  } catch (e) {
    console.error('Move failed', e)
    j.lastCmd = { cmd_id: 'n/a', accepted: false }
  } finally {
    sending[j.id] = false
  }
}

async function startRun() {
  try {
    const r = (await startRunApi({}))
    currentRunId.value = r?.data?.run_id ?? null
    recording.value = currentRunId.value !== null
  } catch (e) {
    console.error(e)
    recording.value = false
  }
}
async function stopRun() {
  if (!currentRunId.value) { recording.value = false; return }
  try {
    await stopRunApi({ path: { run_id: currentRunId.value } })
  } catch (e) {
    console.error(e)
  }
  currentRunId.value = null
  recording.value = false
}

// --- lifecycle ---
onMounted(() => { loadJoints() })
onBeforeUnmount(() => { joints.value.forEach(j => j.ws?.close()) })
</script>
