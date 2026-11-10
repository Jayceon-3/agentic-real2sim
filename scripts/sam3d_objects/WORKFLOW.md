# Great Lakes：从视频到单物体 GLB

这套入口复用已经安装的 **Pi3X、SAM3 和 SAM 3D Objects 独立环境**，不重新安装或
升级它们。每个 `CASE` 固定一个视频、源帧、物体和文字提示；模型阶段可重复运行，
每次产生新的目录。人工检查 mask 与最终资产分别记录，成功退出不代表视觉验收。

```text
环境路径检查 → 准备源帧 → SAM3 候选 → [人工看图并选 mask]
                                       ↓
                           输入校验 → SAM 3D → GLB
                                       ↓
                             [人工 Blender 检查] → 打包

新房间可选：Pi3X + SAM3 + Open3D → 参考几何/相机（单独检查）
已有 Office48 参考直接复用，不需要为了生成一个家具重新推理。
```

## 0. 同步代码和配置路径

在 Great Lakes 现有 `agentic-real2sim` 仓库中操作。先同步新增代码。
默认运行目录为 `~/eecs442_scratch/real2sim/sam3d-objects`。若旧环境放在其他位置：

```bash
cp configs/sam3d_objects.example.sh configs/sam3d_objects.local.sh
# 编辑 local.sh 中的 SAM3_PY、SAM3_RUNTIME、PI3X_PY 等实际路径。
```

`local.sh` 已忽略提交，不放 token。每个新终端执行：

```bash
source scripts/sam3d_objects/paths.sh
bash scripts/sam3d_objects/setup.sh
```

这是文件路径检查，不加载模型、不需要 GPU。首次迁移到新机器仍需按官方文档安装
环境和授权权重；该脚本不会伪造 runtime.json 或自动修补依赖。
额外检查新房间所需 Pi3X/Open3D 环境：

```bash
bash scripts/sam3d_objects/setup.sh --reference
```

模型依赖曾遇到的修复仍由现有安装提供：Kaolin 0.17.0 本地编译，CUDA 使用集群
12.1.1，推理入口在运行副本中修正 CUDA_HOME。不要重新安装预编译 Kaolin 来替换它。

## 1. CPU：准备一个 case

使用新目录；不要指向之前已经存在的手工实验目录。

```bash
export CASE="$SAM3D_PROJECT_ROOT/outputs/sam3d-cases/office48-cabinet-f000-v001"

bash scripts/sam3d_objects/run.sh prepare \
  --case "$CASE" \
  --video "$SAM3D_PROJECT_ROOT/data/local/office48/source.mp4" \
  --frame 0 \
  --object-id office48-wall-cabinet \
  --label "wall-mounted wooden cabinet" \
  --bbox-relative 0.80 0.10 0.99 0.64
```

如果已有 `reference_build.json`，可额外传入 `--reference-build /absolute/reference_build.json`。
它记录路径与哈希，不重新计算参考，也不代替参考视觉审核。

- `--frame` 是零基原视频帧号，不是 Blender 帧号。
- `--label` 就是输入 SAM3 的文字 prompt。
- `--bbox-relative` 为左、上、右、下，范围 0–1；它会按原图尺寸转换。
- 也可用 `--bbox LEFT TOP RIGHT BOTTOM` 指定原图像素，不能同时使用两种框。
- 上述 Office48 框是已经用过的粗定位，不是任意柜体通用框。

准备阶段调用 **Pi3X 环境的 Python + 已有解码工具**抽取原图，不加载 Pi3X 模型。
`source/` 保存原图、视频哈希、帧号、解码器报告时间和尺寸；`sam3-request.json` 保存提示。
换源帧、文字或选择框时建立新 case，不手动修改这些已绑定的文件。
该步骤不需要 GPU，但视频解码应在允许的计算资源中运行，避免在登录节点做长视频重活。

## 2. GPU：选择交互式或 batch，两者选一

### 交互式

登录节点执行下列命令，默认申请两小时 A40，并自动进入计算节点：

```bash
bash scripts/sam3d_objects/gpu.sh
```

可以覆盖时长：`bash scripts/sam3d_objects/gpu.sh --time=01:00:00`。
已在 Slurm allocation 中时脚本会拒绝再次申请。计算节点的新 shell 中：

```bash
cd /你的实际路径/agentic-real2sim
source scripts/sam3d_objects/paths.sh
export CASE="$SAM3D_PROJECT_ROOT/outputs/sam3d-cases/office48-cabinet-f000-v001"
```

若做直接底层 `infer.py` 调用，可 `source scripts/sam3d_objects/env.sh`。
下面的 `run.sh generate` 会自动激活环境，其他阶段则用各自的 Python。

### Batch（避免 SSH 断线停止任务，推荐）

在登录节点先 source `paths.sh` 并设置绝对路径 `CASE`，直接提交阶段：

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch segment --case "$CASE"
```

不需要事先运行 `gpu.sh` 或 `salloc`。审核后用同一个入口提交 `generate`。
每个作业独立申请一张 A40，默认两小时，不自动把人工审核前后两阶段连起来。
同一 case 禁止并发写入；仍应自己控制同一 allocation 只运行一个 GPU 任务。
更改 account、partition 或时限时，Slurm 参数放在脚本文件名之前。

## 3. SAM3 分割，停下来审核

在交互式 GPU 节点：

```bash
bash scripts/sam3d_objects/run.sh segment --case "$CASE"
bash scripts/sam3d_objects/run.sh status --case "$CASE"
```

日志和候选保存在：

```text
CASE/stages/segment-日期-随机后缀/
  console.log
  segmentation_receipt.json
  results/manifest.json
  results/office48-wall-cabinet/text_0_overlay.jpg
  results/office48-wall-cabinet/text_0_cutout.png
  results/office48-wall-cabinet/text_0_mask.png
  ...其他候选
```

这里分别执行文字提示和框提示，自动推荐只是建议。检查完整源图、overlay、cutout 和
黑白 mask，确保选中完整可见物体，排除背景，没有大面积漏选。不要按 score 直接宣布通过。

可把当前候选打成小包下载，无须整个 case 都复制：

```bash
bash scripts/sam3d_objects/run.sh bundle --case "$CASE" --kind review \
  --out "$SAM3D_PROJECT_ROOT/outputs/office48-cabinet-mask-review-001.tar.gz"
```

用本地终端 `scp dingxuan@greatlakes.arc-ts.umich.edu:/远端实际路径/该包.tar.gz outputs/`，
再 `tar -xzf outputs/该包.tar.gz -C outputs/`。远端原 case 保留，不移动它。
在本地看图期间无需一直占用交互式 GPU；之后可单独提交生成作业。

## 4. CPU：登记实际选中的候选

只有实际看过后才执行；下面记录了这次选择 `text_0` 的示例：

```bash
bash scripts/sam3d_objects/run.sh review-mask --case "$CASE" \
  --variant text_0 --reviewed --reviewer dingxuan \
  --note "Inspected overlay and cutout: complete visible cabinet, background excluded."
```

每次审核产生独立的 `review-mask-*` 目录，包含 `mask.png`、来源元数据 `source.json`、
以及带哈希的 `review.json`。它不会改写 SAM3 的原始候选。默认审核最新分割；若要审核
更早一轮，加 `--segmentation "$CASE/stages/具体segment目录"`。

没有审核记录、源图变化、候选被修改或已选 mask 变化时，生成会拒绝继续。
这些是输入一致性检查，不是自动视觉质量评分。

## 5. 校验输入，再生成 GLB

只校验，不加载权重：

```bash
bash scripts/sam3d_objects/run.sh generate --case "$CASE" --validate-only
```

检查 validation 输出的 overlay 后，交互式 GPU 中运行：

```bash
bash scripts/sam3d_objects/run.sh generate --case "$CASE" --seed 42 --save-splat
```

或在登录节点提交 batch：

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch generate \
  --case "$CASE" --seed 42 --save-splat
```

无需手填 output 时间戳。每次生成有独立目录、日志及之前 wrapper 的完整报告：

```text
CASE/stages/generate-日期-随机后缀/
  console.log
  command.json
  stage.json
  results/object.glb
  results/pose.json
  results/report.json
  results/inputs/...
```

重复性能实验可以在同一 reviewed case 多次运行 generate，固定 seed 和导出选项。
每次仍重新启动模型；这里没有模型常驻 worker，也没有自动把同一次结果当作新推理。
`stage.json.wall_seconds` 是该控制阶段的观测耗时，`results/report.json` 是推理 wrapper
的分阶段耗时，两者测量边界不同，Slurm 排队时间均不包含在其中。

## 6. Blender 审核与保存结果

下载 GLB，先在空 Blender 场景检查正面、侧面、背面、材质、保存重开，再记录：

```bash
bash scripts/sam3d_objects/run.sh review-result --case "$CASE" \
  --reviewed --reviewer dingxuan --verdict usable \
  --note "Inspected geometry/materials and reopened the saved Blender scene."
```

如果实际不合格，使用 `--verdict reject` 并记录原因。该记录只针对生成的单资产，
不代表尺度对齐、物体接触、场景重建已通过。截图或 Blender 保存文件可另放本地实验目录。

打包最新生成、对应的审核 mask、输入、配置和日志：

```bash
bash scripts/sam3d_objects/run.sh bundle --case "$CASE" --kind result \
  --out "$SAM3D_PROJECT_ROOT/outputs/office48-cabinet-result-001.tar.gz"
```

输出包必须在 case 外，且不能覆盖已有包。包用于备份与审核，内部记录仍保留原始远端
绝对路径，不宣称解压后能直接在另一台机器恢复执行。下载到本地 ignored `outputs/`。
大资产不提交 Git，小型实验总结、代码和协议才入 Git。

## 可选：确实需要新 Pi3X 房间参考时

已有 Office48 参考无需执行本节。新视频的 GPU 节点可以运行：

```bash
bash scripts/sam3d_objects/run.sh reference --case "$CASE" --num-frames 32
```

或提交：

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch reference --case "$CASE" --num-frames 32
```

这调用既有 `build_reference`，包含 Pi3X、SAM3 语义分割及 Open3D。它生成近似几何、
相机和源视角叠加图，不生成最终可编辑房间，也不提供独立物体的审核 mask。
参考与单物体分割是两个任务，不会互相替代。查看结果后再决定坐标/尺度对齐方案。

## 失败、断线与重试

- 查看状态：`bash scripts/sam3d_objects/run.sh status --case "$CASE"`。
- Python/子进程失败保留 `stage.json`、`error.txt`、已有 console.log，不选择失败输出。
- 同阶段重试产生新目录；不用删旧失败记录。准备阶段失败则换新 case。
- Slurm 强制超时/OOM 可能留下 `running` 状态。先查 `squeue`/`sacct` 确认旧进程结束，
  再重试。内核文件锁随进程释放，不需要手删锁文件。
- `sbatch` 成功返回只证明提交成功；检查作业 ExitCode、case 状态和模型报告。
- 新 shell 重新 source `paths.sh` 并设置 CASE，不依赖上个 shell 的变量。
- 推理入口仍是 `infer.py`；原先独立运行脚本与 `sam3d_objects.sbatch` 继续保留。

本地测试不使用真实视频解码或 GPU 模型；正式新流程仍需要在 Great Lakes 完成一次
端到端运行验证。已有手工结果可以保留为历史证据，无需为了“补流程”重跑它。
