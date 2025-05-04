<template>
  <UContainer class="py-6">
    <div class="max-w-md mx-auto space-y-6">
      <!-- Controls: delta/freq form and global arm/disarm -->
      <div class="flex flex-col space-y-4">

        <div class="flex justify-center space-x-4">
          <UButton color="warning" @click="armAll">Arm All</UButton>
          <UButton color="success" @click="disarmAll">Disarm All</UButton>
        </div>
      </div>

      <!-- Status Card -->
      <UCard>
        <template #header>
          <div>Joint1 Live Status</div>
        </template>
        <div class="space-y-4 p-4">
          <div class="flex justify-between">
            <span class="font-medium">Position:</span>
            <span>{{ position.toFixed(4) }} turns</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="font-medium">Running:</span>
            <UBadge :color="running ? 'success' : 'neutral'">
              {{ running ? 'Yes' : 'No' }}
            </UBadge>
          </div>
          <div class="flex space-x-2">
            <UInput v-model="delta" type="number" step="0.1" label="Delta Turns" class="flex-1" />
            <UInput v-model="freq" type="number" label="Freq (Hz)" class="w-24" />
            <UButton @click="move">Move</UButton>
          </div>
        </div>
        <template #footer>
          <div class="flex justify-end p-4 pt-0 space-x-2">
            <UButton @click="stop" variant="outline">Stop</UButton>
            <UButton color="warning" @click="calibrate">Calibrate</UButton>
            <UButton color="warning" @click="configure">Configure</UButton>
          </div>
        </template>
      </UCard>
    </div>
    <UCard>
      <template #header>CAN Bus Log</template>
      <div class="p-2 h-40 overflow-auto font-mono text-xs bg-gray-50">
        <div v-for="(e, i) in canLog" :key="i">
          {{ e.ts.toFixed(3) }} → {{ e.id }} : {{ e.data }}
        </div>
      </div>
      <template #footer>
          <div class="flex justify-end p-4 pt-0 space-x-2">
            <UButton @click="stopCanLog" variant="outline">Stop</UButton>
            <UButton color="warning" @click="startCanLog">Start</UButton>
          </div>
        </template>
    </UCard>
  </UContainer>
</template>

<script setup lang="ts">

const position = ref(0)
const running = ref(false)
const delta = ref(0.0)
const freq = ref(100)
const calState = ref(3)
const saveConfig = ref(false)
let ws: WebSocket
let wsLog: WebSocket
interface CanEntry { ts: number; id: string; data: string }
const canLog = ref<CanEntry[]>([])

function startCanLog() {
  wsLog = new WebSocket("ws://localhost:8000/ws/canlog")
  wsLog.onmessage = ev => {
    const entry: CanEntry = JSON.parse(ev.data)
    canLog.value.unshift(entry)
    if (canLog.value.length > 200) canLog.value.pop()   // cap length
  }
}

function stopCanLog() {
  wsLog.close()
}

onMounted(() => {
  ws = new WebSocket('ws://127.0.0.1:8000/ws/joint/joint1')
  ws.onmessage = event => {
    const data = JSON.parse(event.data)
    position.value = data.position ?? position.value
    running.value = data.running
  }

})

onUnmounted(() => {
  ws.close()
  stopCanLog()
})

async function move() {
  const res = await fetch(`/api/joints/joint1/move?delta=${delta.value}&freq=${freq.value}`, { method: 'POST' })
  console.log('Move:', await res.json())
}

async function armAll() {
  console.log('Arm All:', await (await fetch('/api/joints/arm-all', { method: 'POST' })).json())
}

async function disarmAll() {
  console.log('Disarm All:', await (await fetch('/api/joints/disarm-all', { method: 'POST' })).json())
}

async function calibrate() {
  const res = await fetch(`/api/joints/joint1/calibrate?state=${calState.value}&save_config=${saveConfig.value}`, { method: 'POST' })
  console.log('Calibrate:', await res.json())
}

async function configure() {
  try {
    const url = `/api/joints/joint1/configure`

    const res = await fetch(url, { method: 'POST' })
    const data = await res.json()
    console.log('Configure result:', data)
  } catch (err) {
    console.error('Configure error:', err)
  }
}

async function stop() {
  console.log('Stop:', await (await fetch('/api/joints/joint1/stop', { method: 'POST' })).json())
}
</script>