---
name: bohrium-job
description: "Manage Bohrium compute jobs primarily via bohr CLI, with openapi.dp.tech API as fallback. Use when: user asks about submitting/listing/killing/deleting compute jobs on Bohrium, checking job logs, or monitoring job status. NOT for: node management, image management, or project management."
---

# SKILL: Bohrium 任务 (Job) 管理

## 概述

管理 Bohrium 平台的计算任务。默认优先使用 `bohr` CLI；仅当 CLI 缺少能力、报 `/dev/tty` 相关错误、或被环境限制卡住时，才回退到 `openapi.dp.tech` API。

这个 Skill 现在按 4 个子流程组织：

1. 提交任务
2. 轮询与状态查询
3. 失败处理与重试
4. 结果汇总与下载

## 认证配置

认证信息来自 shell 环境变量，已在 `.bashrc` 中配置：

- `BOHRIUM_ACCESS_KEY`
- `BOHRIUM_PROJECT_ID`
- 兼容别名：`ACCESS_KEY`、`PROJECT_ID`

执行命令前如果环境变量为空，先加载 `.bashrc`：

```bash
source ~/.bashrc
echo "${BOHRIUM_PROJECT_ID:-$PROJECT_ID}"
```

## 前置条件

优先确认 `bohr` CLI 和 Bohrium 环境变量可用：

```bash
source ~/.bashrc
export PATH="$HOME/.bohrium:$PATH"
bohr version
echo "${BOHRIUM_PROJECT_ID:-$PROJECT_ID}"
```

## 1. 提交任务

### 单个任务

简单场景优先直接用 `bohr` 提交：

```bash
source ~/.bashrc
bohr job submit \
  -m "registry.dp.tech/dptech/deepmd-kit:3.1.1" \
  -t "c4_m15_1 * NVIDIA T4" \
  -c "python train.py" \
  -p ./input_dir/ \
  --project_id "${BOHRIUM_PROJECT_ID:-$PROJECT_ID}" \
  -n "my-job-name"
```

复杂场景优先用 `job.json`：

```bash
bohr job submit -i job.json -p ./input_dir/
```

关键字段：

- `image_address`: 必须是完整镜像地址
- `machine_type`: 机器规格
- `command`: 用相对路径，不要写死工作目录
- `project_id`: 项目 ID
- `result_path`: 自动下载目录
- `max_reschedule_times`: 异常中断自动重试次数

### 批量任务

批量任务优先用现成脚本：

```bash
source ~/.bashrc
python /root/mt_sim_proj_management/backend/skills/bohrium-job/batch_submit.py \
  --job_json ./job.json \
  --input_dirs exp1/ exp2/ exp3/ \
  --group "batch-run"
```

这个脚本会：

- 可选创建 job group
- 按输入目录逐个提交
- 自动生成任务名
- 输出成功/失败统计

## 2. 轮询与状态查询

### 快速查看

```bash
source ~/.bashrc
bohr job list -n 10
bohr job list -r
bohr job list -p
bohr job list -f
bohr job describe -j 22153612 --json
bohr job log -j 22153612
```

### 持续轮询

持续关注活跃任务时，优先用轮询脚本：

```bash
source ~/.bashrc
python /root/mt_sim_proj_management/backend/skills/bohrium-job/poll_jobs.py --interval 60
python /root/mt_sim_proj_management/backend/skills/bohrium-job/poll_jobs.py --once
```

这个脚本会：

- 汇总 Running + Pending 任务
- 打印简洁状态表
- 适合“看一下提交任务都状态”这类请求

## 3. 失败处理与重试

常用操作：

```bash
bohr job terminate 22153612
bohr job kill 22153612
bohr job delete 22153612
```

语义区别：

- `terminate`: 保留结果，任务状态转 completed
- `kill`: 不保留结果，任务记录保留
- `delete`: 删除结果和任务记录

失败排查优先顺序：

1. 看 `bohr job describe`
2. 看 `bohr job log`
3. 检查 `command` 是否用了错误路径
4. 检查镜像地址和机器规格
5. 必要时提高 `max_reschedule_times`

常见失败原因：

- `cd /root/input: No such file`: 命令里写了错误绝对路径
- `unsupported protocol scheme \"\"`: Bohrium 环境变量缺失
- `WAF 405`: 命令被 WAF 拦截，改成脚本方式执行
- 提交后无输出：`-p` 目录里有大隐藏文件，压缩过慢

## 4. 结果汇总与下载

单个任务：

```bash
bohr job download -j 22153612 -o ./results/
```

任务组：

```bash
bohr job_group download -j 15954383 -o ./results/
```

结果汇总时默认输出：

- 成功 / 失败 / 等待中的任务数量
- 每个任务的 job ID
- 失败任务的原因摘要
- 结果文件保存位置

## 任务组管理

```bash
bohr job_group list -n 10 --json
bohr job_group create -n "experiment-v1" -p 154
bohr job_group terminate 15954383
bohr job_group delete 15954383
bohr job_group download -j 15954383 -o ./results/
```

## API 说明

默认优先用 `bohr` CLI。只有在 CLI 缺少能力、报 `/dev/tty` 相关错误、命令被环境限制卡住、或需要 CLI 不暴露的字段时，才回退到 API。典型场景：

- 按状态过滤复杂查询
- 查看任务配置与底层 token
- 查看快照
- 修改任务名或任务组名

## 关键注意事项

- Bohrium 会自动切到输入目录，不要假设固定路径
- `command` 优先使用相对路径
- `image_address` 必须写完整
- `job_type` 必须是 `container`
- 大任务和长任务建议设置 `max_reschedule_times`
- 批量任务优先配合 `job_group`

## bohr CLI 限制

**bohr CLI 在非 TTY 环境下会挂起**（报错：`open /dev/tty: no such device or address`），这是 CLI 设计问题，不是环境配置问题。症状是 `bohr job submit` 命令超时（60s+ 无响应）。

本 skill 仍然优先尝试 `bohr` CLI；如果出现上述错误或长时间无输出，再切换到 API。

**关键说明**：
- POST 接口路径是 `/openapi/v1/job/create`，不是 `/openapi/v1/jobs`
- GET 查询用 `/openapi/v1/job/list?page=1&pageSize=20`
- 注意：查询接口在 projectId 非 3824565 时报 Permission error，属于 list 接口的过滤逻辑问题，不影响提交
- bohr CLI 是默认优先路径；失败或卡住时再用 API
- 提交任务: `POST https://openapi.dp.tech/openapi/v1/job/create` ✅
- 查询任务: `GET https://openapi.dp.tech/openapi/v1/job/list?page=1&pageSize=20`

**已知的 WAF 拦截**: `/openapi/v1/jobs` 会被 WAF 405 拦截，禁止使用。

## 任务状态码

| status | 含义 | bohr CLI 显示 |
|--------|------|---------------|
| 0 | 等待中 | Pending |
| 1 | 运行中 | Running |
| 2 | 已完成 | Finished |
| 3 | 调度中 | Scheduling |
| -1 | 失败 | Failed |

## 常用镜像

查询当前账号可见镜像：

```bash
source ~/.bashrc
bohr image list --json
bohr image list -t "Basic Image" --json
```

已验证可用于提交的镜像：

| image_address | 说明 |
|---------------|------|
| `registry.dp.tech/dptech/deepmd-kit:3.1.1` | DeePMD-kit |
| `registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4` | GROMACS GPU |
| `registry.dp.tech/dptech/prod-18169/gromacs:v6` | GROMACS |
| `registry.dp.tech/dptech/prod-13375/lammps:gpu-nv` | LAMMPS GPU |

## 常见机器规格

查询当前支持的机器规格：

```bash
source ~/.bashrc
bohr machine list --json
bohr machine list -c gpu --json
```

| machine_type | 说明 |
|--------------|------|
| `c2_m4_cpu` | 2 核 4G 内存 CPU |
| `c4_m8_cpu` | 4 核 8G 内存 CPU |
| `c4_m16_cpu` | 4 核 16G 内存 CPU |
| `c8_m32_cpu` | 8 核 32G 内存 CPU |
| `c16_m32_cpu` | 16 核 32G 内存 CPU |
| `c32_m64_cpu` | 32 核 64G 内存 CPU |
| `c4_m15_1 * NVIDIA T4` | 4 核 15G + 1×T4 GPU |
| `c8_m31_1 * NVIDIA T4` | 8 核 31G + 1×T4 GPU |
| `c16_m62_1 * NVIDIA T4` | 16 核 62G + 1×T4 GPU |
| `c6_m60_1 * NVIDIA 4090` | 6 核 60G + 1×4090 GPU |
| `c12_m64_1 * NVIDIA L4` | 12 核 64G + 1×L4 GPU |
| `c8_m32_1 * NVIDIA V100` | 8 核 32G + 1×V100 GPU |
| `c32_m128_4 * NVIDIA V100` | 32 核 128G + 4×V100 GPU |
