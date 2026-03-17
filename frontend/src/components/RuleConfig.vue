<template>
  <div class="rule-config">
    <el-form :model="form" label-width="120px">
      <el-form-item label="规则名称">
        <el-input v-model="form.name" placeholder="例如：A区到B区违规" />
      </el-form-item>
      
      <el-form-item label="起始区域">
        <el-select v-model="form.from_zone" placeholder="选择起始区域">
          <el-option
            v-for="zone in zones"
            :key="zone.id"
            :label="zone.name"
            :value="zone.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item label="目标区域">
        <el-select v-model="form.to_zone" placeholder="选择目标区域">
          <el-option
            v-for="zone in zones"
            :key="zone.id"
            :label="zone.name"
            :value="zone.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="addRule" :disabled="!isValid">
          添加规则
        </el-button>
      </el-form-item>
    </el-form>
    
    <el-divider />
    
    <h4>已配置规则</h4>
    <el-table :data="rules" style="width: 100%">
      <el-table-column prop="name" label="规则名称" />
      <el-table-column label="违规路径">
        <template #default="{ row }">
          {{ getZoneName(row.from_zone) }} 
          <el-icon><Right /></el-icon>
          {{ getZoneName(row.to_zone) }}
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="状态" width="100">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" @change="updateRules" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ $index }">
          <el-button type="danger" size="small" @click="removeRule($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  zones: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const rules = ref([...props.modelValue])

const form = reactive({
  name: '',
  from_zone: '',
  to_zone: '',
  enabled: true
})

const isValid = computed(() => {
  return form.name && form.from_zone && form.to_zone && form.from_zone !== form.to_zone
})

watch(rules, (newVal) => {
  emit('update:modelValue', [...newVal])
}, { deep: true })

// 监听 props.modelValue 变化，同步更新本地状态
watch(() => props.modelValue, (newVal) => {
  rules.value = [...newVal]
}, { deep: true, immediate: true })

const addRule = () => {
  if (form.from_zone === form.to_zone) {
    ElMessage.warning('起始区域和目标区域不能相同')
    return
  }
  
  rules.value.push({
    id: `rule_${Date.now()}`,
    name: form.name,
    from_zone: form.from_zone,
    to_zone: form.to_zone,
    enabled: true
  })
  
  form.name = ''
  form.from_zone = ''
  form.to_zone = ''
  ElMessage.success('规则添加成功')
}

const removeRule = (index) => {
  rules.value.splice(index, 1)
}

const updateRules = () => {
  emit('update:modelValue', [...rules.value])
}

const getZoneName = (zoneId) => {
  const zone = props.zones.find(z => z.id === zoneId)
  if (!zone) {
    console.warn(`Zone not found: ${zoneId}`)
    return `${zoneId}(已删除)`
  }
  return zone.name
}
</script>

<style scoped>
.rule-config {
  padding: 20px;
}
</style>
