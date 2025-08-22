<template>
    <svg :viewBox="viewBox" class="w-full h-16 bg-white border rounded">
      <path
        :d="pathD"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        class="text-gray-800"
      />
    </svg>
  </template>
  
  <script setup lang="ts">
  type Point = { ts: number; [k: string]: number | null }
  type YKey = 'position' | 'velocity'
    
  const props = withDefaults(
    defineProps<{
      points: Point[]
      yKey: YKey
      height?: number
    }>(),
    { height: 60 }
  )
  
  const pathD = computed(() => {
    const pts = props.points
    if (!pts.length) return ''
  
    const minTs = pts[0].ts
    const maxTs = pts[pts.length - 1].ts
    const span = Math.max(1, maxTs - minTs)
  
    const ys = pts.map((p) => (p[props.yKey] ?? 0) as number)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const ySpan = Math.max(1e-6, maxY - minY)
  
    const H = props.height
    const X = (t: number) => ((t - minTs) / span) * 300
    const Y = (y: number) => H - ((y - minY) / ySpan) * H
  
    let d = `M 0 ${Y(ys[0])}`
    for (let i = 1; i < pts.length; i++) {
      d += ` L ${X(pts[i].ts)} ${Y(ys[i])}`
    }
    return d
  })
  
  const viewBox = computed(() => `0 0 300 ${props.height}`)
  </script>