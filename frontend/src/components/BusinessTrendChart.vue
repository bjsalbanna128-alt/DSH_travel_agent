<script setup lang="ts">
import { computed } from 'vue'
import { formatYuan, type TrendPoint } from '../api/dashboard'

const props = defineProps<{ series: TrendPoint[]; today: string }>()

const WIDTH = 720
const HEIGHT = 220
const PAD = { left: 64, right: 14, top: 14, bottom: 30 }
const innerW = WIDTH - PAD.left - PAD.right
const innerH = HEIGHT - PAD.top - PAD.bottom

const maxFen = computed(() => Math.max(1, ...props.series.flatMap(point => [point.paid_fen, point.refund_fen])))
const ticks = computed(() => [0, maxFen.value / 2, maxFen.value].map(value => ({
  value, y: PAD.top + innerH - (value / maxFen.value) * innerH,
})))

function x(index: number): number {
  if (props.series.length <= 1) return PAD.left + innerW / 2
  return PAD.left + (index / (props.series.length - 1)) * innerW
}

function y(fen: number): number {
  return PAD.top + innerH - (fen / maxFen.value) * innerH
}

function points(key: 'paid_fen' | 'refund_fen'): string {
  return props.series.map((point, index) => `${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(' ')
}

const paidLine = computed(() => points('paid_fen'))
const refundLine = computed(() => points('refund_fen'))

function showLabel(index: number): boolean {
  if (props.series.length <= 14) return true
  return index % 2 === 0 || index === props.series.length - 1
}

function shortDate(value: string): string {
  const [, month, day] = value.split('-')
  return `${Number(month)}/${Number(day)}`
}

function isToday(value: string): boolean {
  return value === props.today
}

function label(fen: number): string {
  return formatYuan(fen)
}
</script>

<template>
  <figure class="trend">
    <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img"
      :aria-label="`每日收款与退款趋势，共 ${series.length} 天，最后一天为今日`">
      <g class="axis">
        <line v-for="tick in ticks" :key="tick.value" :x1="PAD.left" :x2="WIDTH - PAD.right"
          :y1="tick.y" :y2="tick.y" class="grid" />
        <text v-for="tick in ticks" :key="`t-${tick.value}`" :x="PAD.left - 8" :y="tick.y + 4"
          text-anchor="end" class="tick">{{ label(tick.value) }}</text>
      </g>
      <polyline :points="paidLine" class="line line-paid" />
      <polyline :points="refundLine" class="line line-refund" />
      <g v-for="(point, index) in series" :key="point.date">
        <circle :cx="x(index)" :cy="y(point.paid_fen)" :r="isToday(point.date) ? 4 : 2.5"
          :class="['dot', 'dot-paid', { 'dot-today': isToday(point.date) }]">
          <title>{{ point.date }}{{ isToday(point.date) ? '（进行中，当日累计）' : '' }}：收款 {{ label(point.paid_fen) }}，订单 {{ point.orders }} 笔</title>
        </circle>
        <circle :cx="x(index)" :cy="y(point.refund_fen)" :r="2" class="dot dot-refund">
          <title>{{ point.date }}：退款 {{ label(point.refund_fen) }}</title>
        </circle>
        <circle v-if="point.net_fen < 0" :cx="x(index)" :cy="PAD.top + innerH - 2" :r="3"
          class="dot dot-negative">
          <title>{{ point.date }}：当日退款大于收款</title>
        </circle>
        <text v-if="showLabel(index)" :x="x(index)" :y="HEIGHT - 10" text-anchor="middle"
          :class="['tick', { 'tick-today': isToday(point.date) }]">{{ shortDate(point.date) }}</text>
      </g>
    </svg>
    <figcaption class="legend">
      <span class="legend-item"><i class="swatch swatch-paid" />收款</span>
      <span class="legend-item"><i class="swatch swatch-refund" />退款</span>
      <span class="legend-item legend-note">今日为进行中数据（当日累计）</span>
    </figcaption>
  </figure>
</template>

<style scoped>
.trend { margin: 0; }
svg { display: block; width: 100%; height: auto; }
.grid { stroke: #e6ebf2; stroke-width: 1; }
.tick { fill: #4a5e73; font-size: 10px; }
.tick-today { font-weight: 700; fill: #182940; }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; }
.line-paid { stroke: #255b90; }
.line-refund { stroke: #9aa8b8; stroke-dasharray: 4 3; }
.dot { stroke: #fff; stroke-width: 1.5; }
.dot-paid { fill: #255b90; }
.dot-refund { fill: #9aa8b8; }
.dot-today { fill: #fff; stroke: #255b90; stroke-width: 2; }
.dot-negative { fill: #c0392b; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 6px; font-size: .82rem; color: #4a5e73; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.swatch { width: 14px; height: 3px; border-radius: 2px; }
.swatch-paid { background: #255b90; }
.swatch-refund { background: #9aa8b8; }
.legend-note { margin-left: auto; }
</style>
