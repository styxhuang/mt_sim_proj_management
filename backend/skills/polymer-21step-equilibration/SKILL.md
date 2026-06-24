---
name: polymer-21step-equilibration
description: Use when building, relaxing, equilibrating, or submitting GROMACS polymer systems with the 21-step polymer equilibration method, including Bohrium remote runs.
---

# 聚合物 21 步平衡法 (Polymer 21-Step Equilibration)

## 简介
本 Skill 提供用于 GROMACS 中聚合物体系弛豫的 21 步压缩/解压缩平衡法。该方法通过 7 个“加热-冷却-加压”循环，帮助聚合物链克服局部能量势垒，消除初始搭建导致的不合理构象，最终达到稳定且合理的密度。

## 21 步平衡协议详情

整个过程分为 7 个循环，每个循环包含 3 个步骤（高温 NVT、低温 NVT、目标压力 NPT）。
除最后一步外，前 6 个循环的 NPT 步骤时长均为 50 ps。

| 循环 | 步骤 | 系综 | 温度 (K) | 压力 (bar) | 时长 (ps) | 目的 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | 1 | NVT | 600 | - | 50 | 高温退火，增加链段运动 |
| | 2 | NVT | 300 | - | 100 | 降温至室温，稳定构象 |
| | 3 | NPT | 300 | 1000 | 50 | 初始轻微加压 |
| **2** | 4 | NVT | 600 | - | 50 | 高温退火 |
| | 5 | NVT | 300 | - | 100 | 降温 |
| | 6 | NPT | 300 | 30000 | 50 | 极高压压缩，消除空隙 |
| **3** | 7 | NVT | 600 | - | 50 | 高温退火 |
| | 8 | NVT | 300 | - | 100 | 降温 |
| | 9 | NPT | 300 | 50000 | 50 | 最高压压缩，达到最大密度 |
| **4** | 10 | NVT | 600 | - | 50 | 高温退火 |
| | 11 | NVT | 300 | - | 100 | 降温 |
| | 12 | NPT | 300 | 25000 | 50 | 开始逐步解压 |
| **5** | 13 | NVT | 600 | - | 50 | 高温退火 |
| | 14 | NVT | 300 | - | 100 | 降温 |
| | 15 | NPT | 300 | 5000 | 50 | 进一步解压 |
| **6** | 16 | NVT | 600 | - | 50 | 高温退火 |
| | 17 | NVT | 300 | - | 100 | 降温 |
| | 18 | NPT | 300 | 500 | 50 | 接近常压 |
| **7** | 19 | NVT | 600 | - | 50 | 最后一次高温退火 |
| | 20 | NVT | 300 | - | 100 | 降温 |
| | 21 | NPT | 298 | 1 | 800 | 常温常压长程平衡，稳定密度 |

*注：第 21 步之后通常可接常规的成品模拟（如 22npt，298K，1 bar，时长视需求而定）。*

## 分析与验证

平衡完成后，需要检查体系的能量和密度是否收敛。你可以使用预置的脚本自动完成提取和绘图。

### 1. 提取数据 (`extract_energy_density.sh`)
在运行目录中执行提取脚本，它会遍历 `.edr` 文件并使用 GROMACS 的 `gmx energy` 工具提取每一步的能量和密度：
```bash
bash /root/mt_sim_proj_management/backend/skills/polymer-21step-equilibration/scripts/extract_energy_density.sh
```

### 2. 绘制演化曲线 (`plot_energy_density.py`)
使用 Python 脚本读取生成的 `.xvg` 文件，将所有阶段的时间轴拼接，绘制**密度**和**总能量**随总模拟时间变化的曲线。脚本还会自动计算并标注最后 500ps 的平均能量和密度。
```bash
python /root/mt_sim_proj_management/backend/skills/polymer-21step-equilibration/scripts/plot_energy_density.py
```
- **密度验证**：观察最后阶段的密度曲线是否趋于平稳，并与实验值或理论值对比（图例中会显示红色的 Last 500ps 平均密度横线）。
- **能量验证**：总能量应在每一步的末尾达到相对稳定的波动状态（图例中会显示蓝色的 Last 500ps 平均能量横线）。

## 最佳实践
1. **步长设置**：建议使用 `dt = 0.001` (1 fs) 或 `0.002` (2 fs)。在极高压（如 50000 bar）阶段，如果体系崩溃，可尝试减小步长或增加前期的能量最小化步数。
2. **能量最小化**：在执行 21 步平衡前，务必先进行充分的**两步**能量最小化（如 `steep` 算法），彻底消除原子的空间重叠。
3. **温度控制**：高温阶段（600K）的温度应高于聚合物的玻璃化转变温度（Tg）或熔点（Tm），以确保链段有足够的活动能力。如果 600K 导致体系不稳定，可适当降低（如 500K）。
4. **热浴/压浴设置**：在初期的压缩和解压过程（前20步）中，为了保证系统快速稳定，可以使用 `v-rescale`（热浴）搭配 `berendsen` 或 `c-rescale`（压浴）。但是在第 21 步的正式长程平衡以及后续的成品模拟中，**务必将压浴（常被称为热浴设置的一部分）改为 `parrinello-rahman`**，以获得准确的 NPT 系综体积与压力波动。

## 能量最小化 (Energy Minimization)
在进入 21 步平衡法之前，必须执行能量最小化以消除系统内的不合理接触和空间重叠。
建议采用**两步法**的能量最小化：
1. **第一步（em）**：`steep`（最速下降法），步数设定为 50000 步。快速消除局部的极高能量位阻。
2. **第二步（em2）**：可以再次使用 `steep` 或者采用更精细的共轭梯度法 `cg` 进一步优化构象，同样为 50000 步。

生成脚本也会默认生成这两个 `em.mdp` 与 `em2.mdp` 配置文件。

## Bohrium 远端提交
当需要把完整拓扑目录提交到 Bohrium 时，输入目录应至少包含 `system.top`、`system_sanitized.gro`（或 `system.gro`）以及所有被 `system.top` include 的 `.itp` 文件。优先使用已配置的 `bohr` CLI：
```bash
source ~/.bashrc
export PATH="$HOME/.bohrium:$PATH"
bohr job submit -i job.json -p /path/to/topology
```

默认远端镜像与命令：
- 镜像：`registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4`
- GROMACS 命令：`gmx_mpi`
- GPU 机器示例：`c4_m15_1 * NVIDIA T4`，可用 `bohr machine list -c gpu --json` 查询当前支持的 GPU 机型。
- 远端运行前设置 MPI/root 与 PATH 环境变量：`OMPI_ALLOW_RUN_AS_ROOT=1`、`OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`、`PATH=.:$PATH`。
- 能量最小化不是 dynamics，EM 阶段不要给 `mdrun` 设置 `-nstlist`：
  ```bash
  gmx_mpi grompp -f em.mdp -o em.tpr -p topol.top -c system_sanitized.gro -maxwarn 10
  gmx_mpi mdrun -v -deffnm em -gpu_id 0
  ```
- 21 步动力学阶段（NVT/NPT）默认运行模板：
  ```bash
  gmx_mpi grompp -f $i.mdp -o $i.tpr -p topol.top -c $oldgroname.gro -maxwarn 10
  gmx_mpi mdrun -v -deffnm $i -nstlist 80 -gpu_id 0
  ```

在直接跑 21 步前，先提交一个快速 smoke test：`EM -> 100 步短 NVT`。短 NVT 阶段建议先用 `constraints = none` 验证拓扑、坐标、镜像和 `gmx_mpi` 可用；不要从未经最小化的初始结构直接带 `constraints = h-bonds` 启动 MD，否则聚合物/混合物初始构型容易在 step 0 触发 `Constraint error in algorithm Lincs`。

提交后用以下命令检查和下载：
```bash
bohr job describe -j <job_id> --json
bohr job log -j <job_id> -o /path/to/output
bohr job download -j <job_id> -o /path/to/output
```

完整 smoke-test `job.json` 模板见 [bohrium.md](bohrium.md)。

## 附加资源
- 有关如何自动生成 21 步对应的完整 `.mdp` 配置文件，请参阅 [reference.md](reference.md)。
- 有关 Bohrium 提交、结果下载和 smoke test 模板，请参阅 [bohrium.md](bohrium.md)。
