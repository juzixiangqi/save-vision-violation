# AGENTS.md - Coding Guidelines

## Project Overview

仓库违规检测系统 - YOLO-based warehouse violation detection with Vue 3 frontend and FastAPI backend.

## Build/Test/Lint Commands

### Backend (Python)

```bash
# Setup (uses uv package manager)
uv sync                          # Install all dependencies
uv python install 3.12          # Install specific Python version

# Run
uv run python backend/run.py    # Start FastAPI dev server (port 8000)
uv run python backend/test_detection.py  # Run manual tests

# Package management
uv add <package>                # Add dependency
uv add --dev <package>          # Add dev dependency
uv sync --upgrade               # Update dependencies

# Enter venv shell
uv shell
```

**No formal test runner configured.** Tests are run via `test_detection.py` using simple assertions. No linting/formatting tools currently configured (consider adding ruff/black).

### Frontend (Vue 3)

```bash
cd frontend

# Development
npm install                     # Install dependencies
npm run dev                     # Start dev server (port 5173)

# Build
npm run build                   # Production build
npm run preview                 # Preview production build
```

**No ESLint/Prettier configured.** Consider adding for code consistency.

### Docker Services

```bash
docker-compose up -d            # Start Redis (6379) and RabbitMQ (5673/15673)
docker-compose down             # Stop services
```

## Code Style Guidelines

### Python (Backend)

#### Imports
- Group imports: stdlib → third-party → local modules
- Use absolute imports with `from app.module import ...`
- Add `sys.path.insert(0, ...)` only in entry scripts

```python
import sys
import os
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

from app.config.models import Zone
from app.core.detector import YOLODetector
```

#### Formatting
- **Indentation**: 4 spaces
- **Line length**: ~100 characters (no strict limit observed)
- **Quotes**: Double quotes for strings
- **Trailing commas**: Not strictly enforced

#### Naming Conventions
- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `POSE_KEYPOINTS`)
- **Private**: Prefix with underscore `_private_method`

#### Types
- Use type hints for function parameters and return types
- Use `from typing import ...` for generics (List, Dict, Optional, etc.)
- Use Pydantic BaseModel for API/data models

```python
from typing import List, Dict, Tuple, Optional

def process_frame(frame: np.ndarray, camera_id: str) -> Tuple[List[Detection], List[Pose]]:
    ...
```

#### Error Handling
- Use try/except with specific error logging
- Print errors with descriptive prefixes: `print(f"[Context] Error: {e}")`
- Return None or empty collections on failure rather than raising

```python
try:
    result = some_operation()
except Exception as e:
    print(f"[ProcessFrame] Error: {e}")
    return []
```

#### Docstrings
- Use Chinese docstrings for Chinese project context
- Triple double quotes `"""`

```python
def detect(self, frame: np.ndarray) -> Tuple[List[Detection], List[Pose]]:
    """检测人员和姿态"""
    ...
```

### Vue 3 (Frontend)

#### File Structure
```
Component.vue
├── <template>     # HTML template
├── <script setup> # Composition API
└── <style scoped> # Component styles
```

#### Script Setup (Composition API)
- Use `<script setup>` syntax exclusively
- Use `ref()` for reactive state
- Use `computed()` for derived state
- Prefix internal variables with underscore if needed

```javascript
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const count = ref(0)
const doubled = computed(() => count.value * 2)

onMounted(() => {
  // initialization
})
</script>
```

#### Naming Conventions
- **Components**: `PascalCase.vue` (e.g., `ZoneEditor.vue`)
- **Variables/Functions**: `camelCase`
- **Stores**: `useXxxStore` (e.g., `useConfigStore`)
- **API modules**: Group by feature (config, zones, rules, monitor)

#### Imports
- Group: Vue core → Vue ecosystem → UI library → local modules
- Use `@/` alias for src directory

```javascript
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '../api'
import ViolationList from '../components/ViolationList.vue'
```

#### API Pattern
Create centralized API module with axios instance:

```javascript
// api/index.js
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export default {
  getConfig: () => api.get('/config'),
  updateConfig: (config) => api.put('/config', config),
  // ...
}
```

#### Pinia Store Pattern
Use Composition API style stores:

```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useConfigStore = defineStore('config', () => {
  // State
  const config = ref(null)
  
  // Getters
  const isConfigured = computed(() => config.value !== null)
  
  // Actions
  async function loadConfig() {
    // implementation
  }
  
  return { config, isConfigured, loadConfig }
})
```

#### Element Plus Usage
- Use scoped styles for component-specific CSS
- Use `el-*` components with kebab-case in templates
- Use `ElMessage` for notifications

```vue
<template>
  <el-button type="primary" @click="handleClick">按钮</el-button>
  <el-tag type="success">状态</el-tag>
</template>

<style scoped>
.my-component {
  padding: 20px;
}
</style>
```

#### Error Handling
- Use `ElMessage.error()` for user-facing errors
- Use `console.error()` for debugging
- Wrap async operations in try/catch

```javascript
const fetchData = async () => {
  try {
    const response = await api.getData()
    data.value = response.data
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
    console.error('Fetch error:', error)
  }
}
```

## Project Structure

```
save-vision-violation/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers
│   │   ├── config/        # Configuration models & manager
│   │   ├── core/          # Business logic (detector, state_machine, etc.)
│   │   ├── services/      # External services (video_stream, redis, rabbitmq)
│   │   └── utils/         # Utility functions
│   ├── config.yml         # Runtime configuration
│   ├── run.py            # Entry point
│   └── test_detection.py # Manual tests
├── frontend/
│   └── src/
│       ├── api/           # API client modules
│       ├── components/    # Vue components
│       ├── router/        # Vue Router config
│       ├── stores/        # Pinia stores
│       └── views/         # Page-level components
├── pyproject.toml         # Python dependencies (uv)
└── docker-compose.yml     # Redis & RabbitMQ
```

## Key Dependencies

### Backend
- FastAPI 0.109.0 - Web framework
- Pydantic 2.5.3 - Data validation
- Ultralytics 8.1.0 - YOLOv8
- OpenCV, NumPy - Computer vision
- Redis, Pika - Caching & messaging

### Frontend
- Vue 3.4.15 + Vue Router 4.2.5
- Pinia 2.1.7 - State management
- Element Plus 2.5.3 - UI components
- Axios - HTTP client

## Architecture Notes

- **State Management**: Python state machine for tracking, Redis for persistence
- **Communication**: RabbitMQ (port 5673) for violation events
- **API Proxy**: Vite dev server proxies `/api` to backend (port 8000)
- **Detection**: YOLOv8 for person/box detection, pose estimation for action recognition
- **Configuration**: YAML-based with frontend wizard UI

## Testing

Currently uses manual test scripts:
- `backend/test_detection.py` - Integration tests for core logic

**Recommendation**: Add pytest for proper unit testing.

## Git Workflow

- No specific branch strategy documented
- Standard commit messages in Chinese or English acceptable
