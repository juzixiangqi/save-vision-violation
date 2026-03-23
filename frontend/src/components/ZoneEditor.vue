<template>
  <div class="zone-editor">
    <div class="toolbar">
      <el-button type="primary" @click="startDrawing" :disabled="isDrawing">
        <el-icon><Plus /></el-icon> 绘制区域
      </el-button>
      <el-button @click="clearDrawing" :disabled="!isDrawing">
        取消绘制
      </el-button>
      <el-button type="danger" @click="clearAll" v-if="zones.length > 0">
        清除所有
      </el-button>
      <span class="tip" v-if="isDrawing">点击画布添加顶点，双击完成绘制</span>
    </div>
    
    <div class="canvas-container" ref="containerRef">
      <canvas
        ref="canvasRef"
        @click="handleCanvasClick"
        @dblclick="handleCanvasDblClick"
        @mousemove="handleMouseMove"
      />
    </div>
    
    <div class="zone-list" v-if="zones.length > 0">
      <h4>已定义区域</h4>
      <el-table :data="zones" style="width: 100%">
        <el-table-column prop="name" label="名称">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" @change="updateZones" />
          </template>
        </el-table-column>
        <el-table-column label="颜色" width="100">
          <template #default="{ row }">
            <el-color-picker v-model="row.color" size="small" @change="draw" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ $index }">
            <el-button type="danger" size="small" @click="deleteZone($index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  backgroundImage: {
    type: String,
    default: ''
  },
  referenceWidth: {
    type: Number,
    default: 1920
  },
  referenceHeight: {
    type: Number,
    default: 1080
  }
})

const emit = defineEmits(['update:modelValue'])

const canvasRef = ref(null)
const containerRef = ref(null)
const isDrawing = ref(false)
const currentPoints = ref([])
const zones = ref([...props.modelValue])
const mousePos = ref({ x: 0, y: 0 })
const backgroundImage = ref(props.backgroundImage)
const cachedBgImage = ref(null)  // 缓存背景图片对象

// 图片显示参数
const imageDisplayParams = ref({
  scale: 1,
  offsetX: 0,
  offsetY: 0,
  imgWidth: 0,
  imgHeight: 0
})

const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F']

onMounted(() => {
  initCanvas()
  // 如果初始就有背景图片，预加载
  if (props.backgroundImage) {
    const img = new Image()
    img.onload = () => {
      cachedBgImage.value = img
      draw()
    }
    img.src = props.backgroundImage
  }
  draw()
  
  // 监听窗口大小变化，重新调整 canvas
  window.addEventListener('resize', handleResize)
})

watch(() => props.modelValue, (newVal) => {
  zones.value = [...newVal]
  draw()
}, { deep: true })

watch(() => props.backgroundImage, (newVal) => {
  backgroundImage.value = newVal
  // 当背景图片URL变化时，预加载并缓存
  if (newVal) {
    const img = new Image()
    img.onload = () => {
      cachedBgImage.value = img
      draw()
    }
    img.src = newVal
  } else {
    cachedBgImage.value = null
    draw()
  }
})

const initCanvas = () => {
  const canvas = canvasRef.value
  const container = containerRef.value
  canvas.width = container.clientWidth
  canvas.height = 400
}

const updateImageDisplayParams = () => {
  if (!canvasRef.value || !cachedBgImage.value) return
  
  const canvas = canvasRef.value
  const img = cachedBgImage.value
  
  // 计算等比例缩放参数
  const scale = Math.min(canvas.width / img.width, canvas.height / img.height)
  const offsetX = (canvas.width - img.width * scale) / 2
  const offsetY = (canvas.height - img.height * scale) / 2
  
  imageDisplayParams.value = {
    scale,
    offsetX,
    offsetY,
    imgWidth: img.width,
    imgHeight: img.height
  }
}

// 将 canvas 坐标转换为原始图片坐标
const canvasToImageCoords = (canvasX, canvasY) => {
  // 如果没有背景图片，直接使用 canvas 坐标
  if (!cachedBgImage.value) {
    return [canvasX, canvasY]
  }
  const { scale, offsetX, offsetY } = imageDisplayParams.value
  return [
    Math.round((canvasX - offsetX) / scale),
    Math.round((canvasY - offsetY) / scale)
  ]
}

// 将原始图片坐标转换为 canvas 坐标
const imageToCanvasCoords = (imageX, imageY) => {
  // 如果没有背景图片，直接使用图片坐标（等同于 canvas 坐标）
  if (!cachedBgImage.value) {
    return [imageX, imageY]
  }
  const { scale, offsetX, offsetY } = imageDisplayParams.value
  return [
    Math.round(imageX * scale + offsetX),
    Math.round(imageY * scale + offsetY)
  ]
}

const draw = () => {
  if (!canvasRef.value) return
  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  // 绘制背景图片或默认背景
  if (cachedBgImage.value) {
    // 使用缓存的图片对象，避免重复加载
    const img = cachedBgImage.value
    updateImageDisplayParams()
    const { scale, offsetX, offsetY } = imageDisplayParams.value
    ctx.drawImage(img, offsetX, offsetY, img.width * scale, img.height * scale)
    drawZones(ctx)
  } else if (backgroundImage.value) {
    // 图片还在加载中，显示加载提示
    ctx.fillStyle = '#f0f0f0'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#999'
    ctx.font = '14px Arial'
    ctx.textAlign = 'center'
    ctx.fillText('加载背景图片中...', canvas.width / 2, canvas.height / 2)
    drawZones(ctx)
  } else {
    ctx.fillStyle = '#f5f5f5'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    drawZones(ctx)
  }
}

const drawZones = (ctx) => {
  const canvas = canvasRef.value
  // 绘制网格
  drawGrid(ctx, canvas.width, canvas.height)

  // 绘制已保存的区域（将原始图片坐标转换为 canvas 坐标）
  zones.value.forEach((zone) => {
    const canvasPoints = zone.points.map(p => imageToCanvasCoords(p[0], p[1]))
    drawZone(ctx, canvasPoints, zone.color, zone.name)
  })

  // 绘制正在绘制的区域（将原始图片坐标转换为 canvas 坐标）
  if (isDrawing.value && currentPoints.value.length > 0) {
    const canvasPoints = currentPoints.value.map(p => imageToCanvasCoords(p[0], p[1]))
    drawZone(ctx, canvasPoints, '#999999', '绘制中...')

    if (canvasPoints.length > 0) {
      const lastPoint = canvasPoints[canvasPoints.length - 1]
      ctx.beginPath()
      ctx.moveTo(lastPoint[0], lastPoint[1])
      ctx.lineTo(mousePos.value.x, mousePos.value.y)
      ctx.strokeStyle = '#999999'
      ctx.setLineDash([5, 5])
      ctx.stroke()
      ctx.setLineDash([])
    }
  }
}

const drawGrid = (ctx, width, height) => {
  ctx.strokeStyle = '#e0e0e0'
  ctx.lineWidth = 1
  const gridSize = 50
  
  for (let x = 0; x <= width; x += gridSize) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, height)
    ctx.stroke()
  }
  
  for (let y = 0; y <= height; y += gridSize) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(width, y)
    ctx.stroke()
  }
}

const drawZone = (ctx, points, color, name) => {
  if (points.length < 3) return
  
  ctx.beginPath()
  ctx.moveTo(points[0][0], points[0][1])
  
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i][0], points[i][1])
  }
  
  ctx.closePath()
  ctx.fillStyle = color + '33'
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()
  
  points.forEach(point => {
    ctx.beginPath()
    ctx.arc(point[0], point[1], 4, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
  })
  
  if (name) {
    const center = calculateCenter(points)
    ctx.fillStyle = color
    ctx.font = 'bold 14px Arial'
    ctx.textAlign = 'center'
    ctx.fillText(name, center[0], center[1])
  }
}

const calculateCenter = (points) => {
  let sumX = 0, sumY = 0
  points.forEach(p => {
    sumX += p[0]
    sumY += p[1]
  })
  return [sumX / points.length, sumY / points.length]
}

const startDrawing = () => {
  isDrawing.value = true
  currentPoints.value = []
  ElMessage.info('点击画布添加顶点，双击完成绘制')
}

const clearDrawing = () => {
  isDrawing.value = false
  currentPoints.value = []
  draw()
}

const clearAll = () => {
  zones.value = []
  updateZones()
  draw()
}

const handleCanvasClick = (e) => {
  if (!isDrawing.value) return

  const rect = canvasRef.value.getBoundingClientRect()
  const canvasX = e.clientX - rect.left
  const canvasY = e.clientY - rect.top

  // 如果背景图片已加载，将 canvas 坐标转换为原始图片坐标
  if (cachedBgImage.value) {
    const [imgX, imgY] = canvasToImageCoords(canvasX, canvasY)
    currentPoints.value.push([imgX, imgY])
  } else {
    currentPoints.value.push([canvasX, canvasY])
  }

  draw()
}

const handleCanvasDblClick = () => {
  if (!isDrawing.value || currentPoints.value.length < 3) {
    if (currentPoints.value.length < 3) {
      ElMessage.warning('至少需要3个顶点')
    }
    return
  }
  
  const color = colors[zones.value.length % colors.length]
  const zoneIndex = zones.value.length
  const zoneLetter = String.fromCharCode(65 + zoneIndex) // A, B, C, ...
  
  // 使用实际图片尺寸作为参考尺寸
  let refWidth = props.referenceWidth
  let refHeight = props.referenceHeight
  
  if (cachedBgImage.value) {
    refWidth = cachedBgImage.value.width
    refHeight = cachedBgImage.value.height
  }
  
  zones.value.push({
    id: `zone_${zoneLetter.toLowerCase()}`,  // 固定ID: zone_a, zone_b, zone_c
    name: `Zone_${zoneLetter}`,               // 显示名称: Zone_A, Zone_B, Zone_C
    color: color,
    points: [...currentPoints.value],
    reference_width: refWidth,
    reference_height: refHeight
  })
  
  updateZones()
  clearDrawing()
  ElMessage.success('区域添加成功')
}

const handleMouseMove = (e) => {
  const rect = canvasRef.value.getBoundingClientRect()
  const canvasX = e.clientX - rect.left
  const canvasY = e.clientY - rect.top
  mousePos.value = { x: canvasX, y: canvasY }

  if (isDrawing.value) {
    draw()
  }
}

const deleteZone = (index) => {
  zones.value.splice(index, 1)
  updateZones()
  draw()
}

const handleResize = () => {
  // 重新初始化 canvas 尺寸
  initCanvas()
  // 重新计算图片显示参数
  updateImageDisplayParams()
  // 重绘
  draw()
}

const updateZones = () => {
  emit('update:modelValue', [...zones.value])
}

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.zone-editor {
  padding: 20px;
}

.toolbar {
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.tip {
  color: #666;
  font-size: 14px;
  margin-left: 10px;
}

.canvas-container {
  border: 2px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.zone-list {
  margin-top: 20px;
}
</style>
