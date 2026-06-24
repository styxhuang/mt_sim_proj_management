---
name: gromacs-bohrium
description: Run standalone GROMACS simulations on Bohrium with image registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4, gmx_mpi, and GPU machine c4_m15_1 * NVIDIA T4. Use when submitting single-step or custom GROMACS jobs, grompp/mdrun workflows, or non-21-step GROMACS simulations to Bohrium.
---

# GROMACS Bohrium 运行

## 适用场景

用于单独提交 GROMACS 模拟任务到 Bohrium，例如自定义 EM、NVT、NPT、production 或已有 `.mdp/.top/.gro` 的单步/多步脚本。

不用于聚合物 21 步平衡法；21 步法优先使用 `polymer-21step-equilibration`。

## 默认 Bohrium 配置

- 镜像：`registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4`
- GROMACS 命令：`gmx_mpi`
- GPU 机型：`c4_m15_1 * NVIDIA T4`
- 项目 ID：`${BOHRIUM_PROJECT_ID:-$PROJECT_ID}`

## 运行脚本模板

```bash
#!/usr/bin/env bash
set -euo pipefail

export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
export PATH=.:$PATH

i=nvt
oldgroname=em

gmx_mpi grompp -f $i.mdp -o $i.tpr -p topol.top -c $oldgroname.gro -maxwarn 10
gmx_mpi mdrun -v -deffnm $i -nstlist 80 -gpu_id 0
```

## EM 注意事项

能量最小化不是 dynamics，`mdrun` 不要设置 `-nstlist`，否则 GROMACS 会报：

```text
Fatal error:
Can not set nstlist without dynamics
```

EM 使用：

```bash
gmx_mpi grompp -f em.mdp -o em.tpr -p topol.top -c system_sanitized.gro -maxwarn 10
gmx_mpi mdrun -v -deffnm em -gpu_id 0
```

## 提交命令

```bash
source ~/.bashrc
export PATH="$HOME/.bohrium:$PATH"

bohr job submit \
  -m "registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4" \
  -t "c4_m15_1 * NVIDIA T4" \
  -c "bash run.sh" \
  -p ./input_dir \
  --project_id "${BOHRIUM_PROJECT_ID:-$PROJECT_ID}" \
  -n "gromacs-job"
```

## 查询与日志

```bash
bohr job describe -j <job_id> --json
bohr job log -j <job_id>
bohr job download -j <job_id> -o ./results
```
