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
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  backgroundImage: {
    type: String,
    default: ''
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

const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F']

onMounted(() => {
  initCanvas()
  draw()
})

watch(() => props.modelValue, (newVal) => {
  zones.value = [...newVal]
  draw()
}, { deep: true })

watch(() => props.backgroundImage, (newVal) => {
  backgroundImage.value = newVal
  draw()
})

const initCanvas = () => {
  const canvas = canvasRef.value
  const container = containerRef.value
  canvas.width = container.clientWidth
  canvas.height = 400
}

const draw = () => {
  if (!canvasRef.value) return
  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  // 绘制背景图片或默认背景
  if (backgroundImage.value) {
    const img = new Image()
    img.onload = () => {
      // 保持纵横比缩放图片
      const scale = Math.min(canvas.width / img.width, canvas.height / img.height)
      const x = (canvas.width - img.width * scale) / 2
      const y = (canvas.height - img.height * scale) / 2
      ctx.drawImage(img, x, y, img.width * scale, img.height * scale)
      drawZones(ctx)
    }
    img.src = backgroundImage.value
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
  
  // 绘制已保存的区域
  zones.value.forEach((zone) => {
    drawZone(ctx, zone.points, zone.color, zone.name)
  })
  
  // 绘制正在绘制的区域
  if (isDrawing.value && currentPoints.value.length > 0) {
    drawZone(ctx, currentPoints.value, '#999999', '绘制中...')
    
    if (currentPoints.value.length > 0) {
      const lastPoint = currentPoints.value[currentPoints.value.length - 1]
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
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  currentPoints.value.push([x, y])
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
  zones.value.push({
    id: `zone_${Date.now()}`,
    name: `Zone_${String.fromCharCode(65 + zones.value.length)}`,
    color: color,
    points: [...currentPoints.value]
  })
  
  updateZones()
  clearDrawing()
  ElMessage.success('区域添加成功')
}

const handleMouseMove = (e) => {
  const rect = canvasRef.value.getBoundingClientRect()
  mousePos.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
  
  if (isDrawing.value) {
    draw()
  }
}

const deleteZone = (index) => {
  zones.value.splice(index, 1)
  updateZones()
  draw()
}

const updateZones = () => {
  emit('update:modelValue', [...zones.value])
}
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
