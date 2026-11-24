<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import L from 'leaflet'
import type { DayPlan } from '../types/travel'

import 'leaflet/dist/leaflet.css'
import markerIcon from 'leaflet/dist/images/marker-icon.png?url'
import markerIconRetina from 'leaflet/dist/images/marker-icon-2x.png?url'
import markerShadow from 'leaflet/dist/images/marker-shadow.png?url'

const icon = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIconRetina,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

const props = defineProps<{ dayPlans: DayPlan[] }>()
const mapContainer = ref<HTMLElement | null>(null)
let map: L.Map | null = null
const markerLayer = L.layerGroup()

// Amap tiles (works in China, no API key needed for raster tiles)
const AMAP_TILE = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

onMounted(() => {
  if (!mapContainer.value) return

  map = L.map(mapContainer.value).setView([0, 0], 2)
  L.tileLayer(AMAP_TILE, {
    subdomains: '1234',
    attribution: '&copy; 高德地图',
  }).addTo(map)

  markerLayer.addTo(map)
  renderMarkers()
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
  }
})

function renderMarkers() {
  if (!map) return

  markerLayer.clearLayers()
  const allLocs: [number, number][] = []

  function addMarker(name: string, location?: { lat: number; lng: number }, description?: string) {
    if (!location) return
    const { lat, lng } = location
    if (!Number.isFinite(lat) || !Number.isFinite(lng)
      || Math.abs(lat) > 90 || Math.abs(lng) > 180 || (lat === 0 && lng === 0)) return

    const pos: [number, number] = [lat, lng]
    allLocs.push(pos)
    const popup = document.createElement('div')
    const title = document.createElement('strong')
    title.textContent = name
    popup.append(title)
    if (description) popup.append(document.createElement('br'), description)
    L.marker(pos, { icon, title: name, alt: name }).bindPopup(popup).addTo(markerLayer)
  }

  for (const day of props.dayPlans) {
    for (const attraction of day.attractions ?? []) {
      addMarker(attraction.name, attraction.location, attraction.description)
    }
    if (day.hotel) addMarker(day.hotel.name, day.hotel.location)
  }
  if (allLocs.length > 0) {
    map.fitBounds(L.latLngBounds(allLocs), { padding: [30, 30], maxZoom: 15 })
  } else {
    map.setView([0, 0], 2)
  }
}

watch(() => props.dayPlans, renderMarkers, { deep: true })
</script>

<template>
  <div ref="mapContainer" class="mini-map" />
</template>

<style scoped>
.mini-map { width: 100%; height: 240px; border-radius: 8px; margin-bottom: 16px; }
</style>
