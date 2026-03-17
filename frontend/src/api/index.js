import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export default {
  // Config
  getConfig: () => api.get('/config'),
  updateConfig: (config) => api.put('/config', config),
  
  // Cameras
  getCameras: () => api.get('/config/cameras'),
  updateCameras: (cameras) => api.put('/config/cameras', cameras),
  
  // Zones
  getZones: () => api.get('/config/zones'),
  updateZones: (zones) => api.put('/config/zones', zones),
  createZone: (zone) => api.post('/zones', zone),
  updateZone: (id, zone) => api.put(`/zones/${id}`, zone),
  deleteZone: (id) => api.delete(`/zones/${id}`),
  
  // Rules
  getRules: () => api.get('/config/rules'),
  updateRules: (rules) => api.put('/config/rules', rules),
  createRule: (rule) => api.post('/rules', rule),
  updateRule: (id, rule) => api.put(`/rules/${id}`, rule),
  deleteRule: (id) => api.delete(`/rules/${id}`),
  
  // Detection Params
  getDetectionParams: () => api.get('/config/detection-params'),
  updateDetectionParams: (params) => api.put('/config/detection-params', params),
  
  // Monitor
  startMonitoring: () => api.post('/monitor/start'),
  stopMonitoring: () => api.post('/monitor/stop'),
  getStatus: () => api.get('/monitor/status'),
  testFrame: (cameraId) => api.get('/monitor/test-frame', { params: { camera_id: cameraId } }),
  getCameraFrame: (cameraId) => api.get('/monitor/camera-frame', { params: { camera_id: cameraId } }),
  
  // Debug
  debugProcessVideo: (videoPath, frameNumber) => api.post('/monitor/debug-process', null, { 
    params: { video_path: videoPath, frame_number: frameNumber }
  }),
  getVideoInfo: (videoPath) => api.get('/monitor/debug-video-info', { params: { video_path: videoPath } })
}
