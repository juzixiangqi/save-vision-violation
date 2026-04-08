# 变更日志

## 2026-04-08 - 跟踪算法优化：ByteTrack 纯运动跟踪

### 改进内容

**替换 DeepSort 为 ByteTrack 纯运动跟踪器**

#### 问题背景
- DeepSort 依赖外观特征（ReID）进行跟踪
- 俯视角度下外观特征不明显
- 人做动作时 BBox 变化导致外观特征变化 → ID 频繁切换

#### 解决方案
使用 **ByteTrack** 纯运动跟踪算法：
- **不依赖外观特征** - 只使用运动信息（IoU + 距离）
- **卡尔曼滤波预测** - 预测目标位置，提高匹配稳定性  
- **匈牙利算法匹配** - 基于 IoU 进行最优匹配
- **高分/低分两次匹配** - 减少漏检和误检

#### 新增文件

**backend/app/core/byte_tracker.py**
- `ByteTrack` 类 - 纯运动跟踪器核心实现
- `ByteTrackWrapper` 类 - 兼容 DeepSort 接口的包装器
- `Track` 类 - 跟踪对象，包含卡尔曼滤波状态

#### 修改文件

**backend/app/core/violation_checker.py**
- 导入 `ByteTrackWrapper` 替代 `DeepSort`
- 初始化使用 `ByteTrackWrapper(max_age=30, min_hits=3)`

#### 算法特点

**ByteTrack 优势：**
1. **纯运动跟踪** - 只依赖 BBox 位置和大小，不依赖外观
2. **卡尔曼滤波** - 预测运动轨迹，遮挡后仍能恢复
3. **两次匹配策略** - 高分检测优先匹配，低分检测辅助匹配
4. **适合俯视场景** - 人员外观变化大但运动相对稳定

**预期效果：**
- 同一人站在原地做动作，ID 保持稳定
- 人员交叉时 ID 切换减少
- 处理速度提升（无需计算外观特征）

---

## 2026-04-08 - DeepSort Bug 修复

### 修复内容

**修复视频流播放错误**: `either embeddings or frame must be given!`

#### 问题原因
DeepSort 跟踪器在 `update_tracks()` 方法中需要传入实际的图像帧来计算人员外观特征（embeddings），但代码传入了 `frame=None`，导致运行时错误。

#### 修改文件

**backend/app/core/violation_checker.py**
- `process_frame()` 方法新增 `frame: np.ndarray = None` 参数
- 将 `frame` 传递给 DeepSort 的 `update_tracks()` 方法

**backend/app/api/debug_stream.py**
- `process_frame_sync()` 函数：传入 `frame=frame` 参数
- `do_detection()` 函数：传入 `frame=frame` 参数

**backend/app/api/monitor.py**
- `process_frame()` 函数：传入 `frame=frame` 参数

**backend/app/core/debug_visualizer.py**
- `process_video_frame_debug()` 函数：传入 `frame=frame` 参数

### 技术说明

DeepSORT 追踪算法需要原始图像帧来提取 OSNet 外观特征，用于在遮挡或交叉场景中重识别人员。之前传入 `frame=None` 的代码路径会导致：
1. 无法正常计算 embeddings
2. 跟踪器无法验证姿态检测结果
3. 报错并中断视频流

---

## 2025-04-02 - 违规检测系统重大改进

### 新增功能

#### 1. 可视化增强
- **人员ID显示**: 在每个人员边界框上方显示ID（如：P1, P2...）
- **状态颜色区分**: 
  - 🟢 绿色边框 = IDLE（空闲）
  - 🟡 黄色边框 = CARRYING（搬运中）
  - 🔴 红色边框 = OCCLUDED（遮挡/丢失）
- **实时状态显示**: 在人员框旁边显示当前状态和所在区域
- **中文支持**: 修复OpenCV不支持中文的问题，所有界面文字正常显示

#### 2. 追踪算法升级
- **DeepSORT集成**: 使用 `deep-sort-realtime` 库替代原有IOU追踪
  - 基于外观特征（OSNet）+ 运动预测（卡尔曼滤波）
  - 人员交叉时ID保持稳定
  - 遮挡后重识别更准确
  - 支持快速移动场景

#### 3. 姿态检测优化
- **俯视版搬起检测**: 针对天花板45度俯视拍摄优化
  - 考虑透视导致的y轴压缩
  - 放宽手部高度判断
  - 强化水平距离判断
- **简化检测模式**: 移除严格模式，只保留宽松模式
  - 降低漏检率
  - 减少连续帧要求（5帧→2帧）
  - 更容易触发搬起/放下检测

### 技术变更

#### 依赖更新
```toml
[project.dependencies]
# 新增
"deep-sort-realtime>=1.3.0",
"pillow>=10.0.0",
```

安装命令：
```bash
uv sync
```

#### 代码修改

**backend/app/utils/helpers.py**
- 新增 `is_carrying_pose_overhead()`: 针对俯视拍摄的搬起检测
- 删除 `is_carrying_pose()`: 移除严格模式
- 保留 `is_carrying_pose_relaxed()` 和 `is_dropping_pose_relaxed()`

**backend/app/core/debug_visualizer.py**
- 新增中文绘制支持（PIL/Pillow）
- 新增 `_draw_person_with_status()`: 绘制带状态的人员
- 修改 `_draw_info_panel()`: 显示各状态人员统计
- 修改 `_draw_zones()`: 使用中文显示区域名称

**backend/app/core/violation_checker.py**
- 集成 DeepSort 追踪器
- 移除 `use_relaxed_detection` 参数
- 使用新的俯视版搬起检测

**pyproject.toml**
- 添加 `deep-sort-realtime` 和 `pillow` 依赖

### 性能影响

- **DeepSORT**: 增加约5-10ms每帧
- **PIL中文绘制**: 增加约2-3ms每帧
- **总体**: 帧率下降约10-15%，仍能满足实时性（>15fps）

### 已知问题

- Windows系统需要安装中文字体（如黑体、宋体）
- DeepSORT首次运行时可能下载OSNet模型（约10MB）

### 后续计划

- [ ] 支持自定义DeepSORT参数调优
- [ ] 添加追踪性能监控
- [ ] 支持GPU加速（CUDA）
- [ ] 针对特定场景训练专用ReID模型

---

## 之前的版本

### v0.1.0 (2025-03-16)
- 初始版本发布
- 基础YOLO检测（人员+箱子）
- IOU-based人员追踪
- 基础违规检测逻辑
