<template>
  <UContainer class="py-6">
    <!-- Global Arm/Disarm -->
    <div class="max-w-4xl mx-auto mb-6 flex justify-center space-x-4">
      <UButton color="warning" @click="armAll">Arm All</UButton>
      <UButton color="success" @click="disarmAll">Disarm All</UButton>
    </div>

    <!-- Joint Cards -->
    <div class="max-w-4xl mx-auto space-y-6">
      <div v-for="joint in joints" :key="joint.id">
        <UCard>
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-semibold text-lg">{{ joint.id }}</span>
              <UBadge :color="joint.type === 'odrive' ? 'primary' : 'success'">
                {{ joint.type }}
              </UBadge>
            </div>
          </template>

          <div class="space-y-4 p-4">
            <div class="flex justify-between">
              <span class="font-medium">Position:</span> 
              <span>{{ joint.position.toFixed(4) }} turns</span>
            </div>
            <div class="flex justify-between items-center">
              <span class="font-medium">Running:</span>
              <UBadge :color="joint.running ? 'success' : 'neutral'">
                {{ joint.running ? 'Yes' : 'No' }}
              </UBadge>
            </div>
            <div class="flex space-x-2">
              <div class="flex-1">

              <UFormField label="Position">
                <USlider
                  v-model="joint.position"
                  type="number"
                  :min="0"
                  :max="100"
                />
              </UFormField>
            </div>
            <UFormField label="Velocity">
                <UInput
                  v-model="joint.velocity"
                  type="number"
                  step="0.1"
                  label="Velocity"
                  class="w-24"
                />
              </UFormField>
              <UFormField label="Accel">
                <UInput
                  v-model="joint.accel"
                  type="number"
                  step="0.1"
                  label="Accel"
                  class="w-24"
                />
              </UFormField>
              <UFormField label="Hold">
                <UCheckbox
                  v-model="joint.hold"
                  label="Hold"
                />
              </UFormField>
            <UButton @click="move(joint)">Move</UButton>
            </div>
          </div>

          <template #footer>
            <div class="flex justify-end p-4 pt-0 space-x-2">
              <UButton @click="stop(joint)" variant="outline">Stop</UButton>
              <UButton color="warning" @click="calibrate(joint)">Calibrate</UButton>
              <UButton color="warning" @click="configure(joint)">Configure</UButton>
            </div>
          </template>
        </UCard>
      </div>
    </div>

    <!-- CAN Bus Logs -->
    <div class="max-w-4xl mx-auto mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- ODrive bus -->
      <UCard>
        <template #header>can0 (ODrive) Log</template>
        <div class="p-2 h-40 overflow-auto font-mono text-xs bg-gray-50">
          <div
            v-for="(e, i) in canLog.odrive"
            :key="`odrive-${i}`"
          >
            {{ e.ts.toFixed(3) }} → {{ e.id }} : {{ e.data }}
          </div>
        </div>
        <template #footer>
          <div class="flex justify-end p-4 pt-0 space-x-2">
            <UButton @click="stopCanLog('odrive')" variant="outline">
              Stop
            </UButton>
            <UButton color="warning" @click="startCanLog('odrive')">
              Start
            </UButton>
          </div>
        </template>
      </UCard>

      <!-- Moteus bus -->
      <UCard>
        <template #header>can1 (Moteus) Log</template>
        <div class="p-2 h-40 overflow-auto font-mono text-xs bg-gray-50">
          <div
            v-for="(e, i) in canLog.moteus"
            :key="`moteus-${i}`"
          >
            {{ e.ts.toFixed(3) }} → {{ e.id }} : {{ e.data }}
          </div>
        </div>
        <template #footer>
          <div class="flex justify-end p-4 pt-0 space-x-2">
            <UButton @click="stopCanLog('moteus')" variant="outline">
              Stop
            </UButton>
            <UButton color="warning" @click="startCanLog('moteus')">
              Start
            </UButton>
          </div>
        </template>
      </UCard>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { client as apiClient } from '~/client/client.gen'
import * as api from '~/client/sdk.gen'

apiClient.setConfig({ baseUrl: '/api' })

interface JointInfo {
  id: string
  type: 'odrive' | 'moteus'
  initialized: boolean
  position: number
  velocity: number
  accel: number
  hold: boolean
  running: boolean
  ws?: WebSocket
}

interface CanEntry { ts: number; id: string; data: string }

const joints = ref<JointInfo[]>([])
const canLog = reactive({
  odrive: [] as CanEntry[],
  moteus: [] as CanEntry[],
})

let wsLog: Record<'odrive'|'moteus', WebSocket|undefined> = {
  odrive: undefined,
  moteus: undefined,
}

// Fetch joint list and kick off their WS streams (OpenAPI client)
async function loadJoints() {
  const res = await api.listJointsJointsIndexGet()
  const list = res.data ?? []

  joints.value = list.map(j => ({
    // j has { id, type, initialized } from your FastAPI endpoint
    ...(j as { id: string; type: 'odrive'|'moteus'; initialized: boolean }),
    position: 0,
    velocity: 0,
    accel: 0,
    hold: true,
    running: false,
    ws: undefined,
  }))

  // const host = window.location.hostname || '127.0.0.1'
  // // open one WS per joint
  // joints.value.forEach(j => {
  //   const socket = new WebSocket(`ws://${host}:8000/ws/joint/${j.id}`)
  //   socket.onmessage = ev => {
  //     const d = JSON.parse(ev.data)
  //     j.position = d.position ?? j.position
  //     j.running  = d.running
  //   }
  //   j.ws = socket
  // })
}

// Global arm/disarm
async function armAll() {
  const r = await api.armAllJointsArmAllPost()
  console.log('Arm All:', r.data)
}
async function disarmAll() {
  const r = await api.disarmAllJointsDisarmAllPost()
  console.log('Disarm All:', r.data)
}

// Per-joint actions
async function move(j: JointInfo) {
  await api.moveJointJointsJointNameMovePost({
    path: { joint_name: j.id },
    query: {
      position: j.position,
      // Pass optional params only if you want them considered; else omit.
      // If 0 has meaning for you, keep as-is; otherwise gate with undefined.
      velocity: j.velocity,
      accel: j.accel,
      hold: j.hold,
    },
  })
}

async function stop(j: JointInfo) {
  await api.stopJointJointsJointNameStopPost({ path: { joint_name: j.id } })
  j.running = false
}

async function calibrate(j: JointInfo) {
  await api.calibrateJointJointsJointNameCalibratePost({ path: { joint_name: j.id } })
}

async function configure(j: JointInfo) {
  await api.configureJointJointsJointNameConfigurePost({ path: { joint_name: j.id } })
}

// CAN log start/stop (WebSockets not part of OpenAPI; keep as-is)
function startCanLog(bus: 'odrive'|'moteus') {
  const host = window.location.hostname || '127.0.0.1'
  if (wsLog[bus]) return
  const socket = new WebSocket(`ws://${host}:8000/ws/canlog/${bus}`)
  socket.onmessage = ev => {
    const entry: CanEntry = JSON.parse(ev.data)
    canLog[bus].unshift(entry)
    if (canLog[bus].length > 200) canLog[bus].pop()
  }
  wsLog[bus] = socket
}

function stopCanLog(bus: 'odrive'|'moteus') {
  wsLog[bus]?.close()
  wsLog[bus] = undefined
}

// Lifecycle
onMounted(() => {
  loadJoints()
  // startCanLog('odrive')
})

onUnmounted(() => {
  joints.value.forEach(j => j.ws?.close())
  // stopCanLog('odrive')
})
</script>