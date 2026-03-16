import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useConfigStore = defineStore('config', () => {
  // State
  const config = ref(null)
  const zones = ref([])
  const rules = ref([])
  const cameras = ref([])
  const detectionParams = ref(null)
  const loading = ref(false)

  // Getters
  const isConfigured = computed(() => {
    return zones.value.length > 0 && rules.value.length > 0 && cameras.value.length > 0
  })

  // Actions
  async function loadConfig() {
    loading.value = true
    try {
      const response = await api.getConfig()
      config.value = response.data
      zones.value = response.data.zones || []
      rules.value = response.data.violation_rules || []
      cameras.value = response.data.cameras || []
      detectionParams.value = response.data.detection_params
    } catch (error) {
      console.error('Failed to load config:', error)
    } finally {
      loading.value = false
    }
  }

  async function saveZones(newZones) {
    try {
      await api.updateZones(newZones)
      zones.value = newZones
    } catch (error) {
      console.error('Failed to save zones:', error)
      throw error
    }
  }

  async function saveRules(newRules) {
    try {
      await api.updateRules(newRules)
      rules.value = newRules
    } catch (error) {
      console.error('Failed to save rules:', error)
      throw error
    }
  }

  async function saveCameras(newCameras) {
    try {
      await api.updateCameras(newCameras)
      cameras.value = newCameras
    } catch (error) {
      console.error('Failed to save cameras:', error)
      throw error
    }
  }

  async function saveDetectionParams(params) {
    try {
      await api.updateDetectionParams(params)
      detectionParams.value = params
    } catch (error) {
      console.error('Failed to save detection params:', error)
      throw error
    }
  }

  return {
    config,
    zones,
    rules,
    cameras,
    detectionParams,
    loading,
    isConfigured,
    loadConfig,
    saveZones,
    saveRules,
    saveCameras,
    saveDetectionParams
  }
})
