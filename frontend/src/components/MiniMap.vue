<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import L from 'leaflet'
import type { DayPlan } from '../types/travel'

// Fix Leaflet default icon paths (broken by bundlers)
import 'leaflet/dist/leaflet.css'
// @ts-ignore
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const props = defineProps<{ dayPlans: DayPlan[] }>()
const mapContainer = ref<HTMLElement | null>(null)
let map: L.Map | null = null
const markerLayer = L.layerGroup()

// Amap tiles (works in China, no API key needed for raster tiles)
const AMAP_TILE = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

onMounted(() => {
  if (!mapContainer.value) return

  map = L.map(mapContainer.value).setView([30.67, 104.06], 12)
  L.tileLayer(AMAP_TILE, {
    subdomains: '1234',
    attribution: '&copy; 高德地图',
  }).addTo(map)

  markerLayer.addTo(map)
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
  }
})

watch(() => props.dayPlans, (plans) => {
  if (!map || plans.length === 0) return

  markerLayer.clearLayers()

  const allLocs: [number, number][] = []

  plans.forEach((dp) => {
    dp.attractions?.forEach((a) => {
      if (a.location?.lat && a.location?.lng) {
        const pos: [number, number] = [a.location.lat, a.location.lng]
        allLocs.push(pos)
        L.marker(pos)
          .bindPopup(`<b>${a.name}</b><br>${a.description || ''}`)
          .addTo(markerLayer)
      }
    })

    if (dp.hotel?.location?.lat && dp.hotel?.location?.lng) {
      const pos: [number, number] = [dp.hotel.location.lat, dp.hotel.location.lng]
      allLocs.push(pos)
      L.marker(pos, {
        icon: L.icon({
          iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
          iconSize: [25, 41],
          iconAnchor: [12, 41],
        }),
      }).bindPopup(`<b>${dp.hotel.name}</b>`).addTo(markerLayer)
    }
  })

  if (allLocs.length > 0) {
    map.fitBounds(L.latLngBounds(allLocs), { padding: [30, 30] })
  }
}, { deep: true })
</script>

<template>
  <div ref="mapContainer" class="mini-map" />
</template>

<style scoped>
.mini-map { width: 100%; height: 240px; border-radius: 8px; margin-bottom: 16px; }
</style>
