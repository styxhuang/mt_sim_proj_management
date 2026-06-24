# Bohrium GROMACS 提交参考

本页用于把已生成的 GROMACS 聚合物拓扑目录提交到 Bohrium。拓扑目录应包含：

- `system.top`
- `system_sanitized.gro`，没有时可改用 `system.gro`
- `system.top` 中 `#include` 的全部 `.itp`

## 前置检查

```bash
source ~/.bashrc
export PATH="$HOME/.bohrium:$PATH"
bohr version
echo "${BOHRIUM_PROJECT_ID:-$PROJECT_ID}"
```

如果环境里没有 `boh`，使用 `bohr`。常见安装位置是 `$HOME/.bohrium/bohr`。

## 推荐 Smoke Test

先跑 `EM -> 短 NVT` 验证镜像、`gmx_mpi`、拓扑和坐标都可用，再提交完整 21 步平衡。短 NVT 使用 `constraints = none`，避免未充分弛豫的初始结构在 step 0 触发 LINCS constraint error。

将下面内容保存为 `job_em_nvt.json`。按需替换 `project_id`、`result_path`、`machine_type` 和任务名。

完整 21 步平衡在 GPU 机型上使用下面的模板。注意：EM 不是 dynamics，不能设置 `-nstlist`。

```bash
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
export PATH=.:$PATH

gmx_mpi grompp -f em.mdp -o em.tpr -p topol.top -c system_sanitized.gro -maxwarn 10
gmx_mpi mdrun -v -deffnm em -gpu_id 0

gmx_mpi grompp -f $i.mdp -o $i.tpr -p topol.top -c $oldgroname.gro -maxwarn 10
gmx_mpi mdrun -v -deffnm $i -nstlist 80 -gpu_id 0
```

```json
{
  "job_name": "polymer-gromacs-em-nvt-smoke",
  "job_type": "container",
  "image_address": "registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4",
  "machine_type": "c4_m15_1 * NVIDIA T4",
  "project_id": 929872,
  "command": "set -euo pipefail\nmkdir -p results\ncollect_results() {\n  cp em.mdp nvt.mdp *.log *.stdout *.tpr *.gro *.edr *.cpt *.mdp results/ 2>/dev/null || true\n  cp step*.pdb results/ 2>/dev/null || true\n}\ntrap collect_results EXIT\ncat > em.mdp <<'EOF'\nintegrator               = steep\nnsteps                   = 500\nemtol                    = 10000\nemstep                   = 0.001\nnstlog                   = 50\nnstenergy                = 50\ncutoff-scheme            = Verlet\nrlist                    = 1.0\ncoulombtype              = PME\nrcoulomb                 = 1.0\nvdwtype                  = Cut-off\nrvdw                     = 1.0\nDispCorr                 = EnerPres\npbc                      = xyz\nEOF\ncat > nvt.mdp <<'EOF'\nintegrator               = md\ndt                       = 0.0005\nnsteps                   = 100\nnstxout-compressed       = 10\nnstenergy                = 10\nnstlog                   = 10\ncontinuation             = no\nconstraint_algorithm     = lincs\nconstraints              = none\ncutoff-scheme            = Verlet\nrlist                    = 1.0\ncoulombtype              = PME\nrcoulomb                 = 1.0\nvdwtype                  = Cut-off\nrvdw                     = 1.0\nDispCorr                 = EnerPres\ntcoupl                   = V-rescale\ntc-grps                  = System\ntau_t                    = 1.0\nref_t                    = 300\npcoupl                   = no\npbc                      = xyz\ngen_vel                  = yes\ngen_temp                 = 300\ngen_seed                 = -1\ncomm-mode                = Linear\nnstcomm                  = 10\nEOF\ngmx_mpi grompp -f em.mdp -c system_sanitized.gro -p system.top -o em.tpr -po emout.mdp -maxwarn 10 > em_grompp.log 2>&1\ngmx_mpi mdrun -deffnm em -ntomp 4 -nb cpu -pme cpu > em_mdrun.stdout 2>&1\ngmx_mpi grompp -f nvt.mdp -c em.gro -p system.top -o nvt.tpr -po nvtout.mdp -maxwarn 10 > nvt_grompp.log 2>&1\ngmx_mpi mdrun -deffnm nvt -ntomp 4 -nb cpu -pme cpu > nvt_mdrun.stdout 2>&1\necho done > results/job.done",
  "log_file": "nvt.log",
  "backward_files": [
    "results"
  ],
  "result_path": "/personal/hbond/demo",
  "max_reschedule_times": 1,
  "max_run_time": 20,
  "nnode": 1
}
```

提交：

```bash
source ~/.bashrc
export PATH="$HOME/.bohrium:$PATH"
bohr job submit -i job_em_nvt.json -p /path/to/topology
```

检查和下载：

```bash
bohr job describe -j <job_id> --json
bohr job log -j <job_id> -o /path/to/output
bohr job download -j <job_id> -o /path/to/output
```

成功标志：

- `bohr job describe` 显示 `statusStr` 为 `Finished`
- `exitCode` 为 `0`
- 结果目录中存在 `results/job.done`
- `nvt.log` 末尾出现 `Finished mdrun`

## 常见失败

- `Constraint error in algorithm Lincs at step 0`：通常是初始结构未充分最小化，或直接带 `constraints = h-bonds` 启动 MD。先跑 EM，并用 `constraints = none` 做短 NVT smoke test。
- `Segmentation fault` 且日志停在 LINCS 错误附近：优先按 LINCS 失败处理，不要先改镜像。
- `gmx_mpi: command not found`：确认镜像为 `registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4`，并且 job 命令里使用 `gmx_mpi`。
- GPU 任务调度慢：用 `bohr machine list -c gpu --json` 换一个当前可用的 GPU 机型。
- `bohr job download` 崩溃但 `bohr job log` 成功：先看日志目录；Bohrium 自动下载可能已经把 `results` 放到 `result_path`。
