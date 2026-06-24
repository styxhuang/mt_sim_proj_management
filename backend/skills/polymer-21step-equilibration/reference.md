# 21步平衡法 MDP 文件参考

为了方便快速搭建聚合物 21 步平衡的模拟，本 Skill 提供了一个 Python 脚本来自动生成所需的 21 个 `.mdp` 文件。

## MDP 文件生成脚本

你可以在工作目录中运行该脚本，它会自动创建一个 `mdp/` 文件夹并在其中生成 `em.mdp`、`em2.mdp`，以及 `1nvt.mdp` 到 `21npt.mdp`。

### 使用方法

1. 执行以下命令自动生成脚本：
   ```bash
   python /root/mt_sim_proj_management/backend/skills/polymer-21step-equilibration/scripts/generate_21_mdp.py
   ```
2. 检查当前目录下生成的 `mdp/` 文件夹。

### 脚本生成的关键参数说明
- **步长 (`dt`)**: 统一使用 `0.001` ps (1 fs)。对于包含高压的聚合物体系，1 fs 较为稳定。
- **控温 (`tcoupl`)**: 使用 `v-rescale`，对于平衡过程，这是快速且准确的热浴。
- **控压 (`pcoupl`)**: 
  - 前 20 步的 NPT 阶段：使用 `Berendsen` 压浴，`tau_p = 2.0`，快速响应压力变化。
  - 第 21 步（正式平衡阶段）：使用 `Parrinello-Rahman` 压浴，`tau_p = 5.0`，以获得正确的体积涨落。
- **截断与静电**: `cutoff-scheme = Verlet`，`coulombtype = PME`，短程截断距离为 `1.0 nm`。
- **边界条件**: 默认生成三维周期性边界条件 `pbc = xyz`。如需针对特定体系（如狭缝孔 `pbc = xy`）进行模拟，请手动修改模板。

## MDP 文件结构示例

### 1. 第 1 步：初始高温 NVT (`1nvt.mdp`)
```ini
integrator               = md
nsteps                   = 50000        ; 50 ps
dt                       = 0.001

tcoupl                   = v-rescale
tc-grps                  = system
tau_t                    = 0.1
ref_t                    = 600

pcoupl                   = no

gen_vel                  = yes          ; 初始步骤分配速度
gen_temp                 = 600
continuation             = no
```

### 2. 第 6 步：极高压 NPT (`6npt.mdp`)
```ini
integrator               = md
nsteps                   = 50000        ; 50 ps
dt                       = 0.001

tcoupl                   = v-rescale
tc-grps                  = system
tau_t                    = 0.1
ref_t                    = 300

pcoupl                   = Berendsen    ; 平衡阶段使用 Berendsen
pcoupltype               = isotropic
tau_p                    = 2.0
ref_p                    = 30000        ; 30000 bar 高压

gen_vel                  = no
continuation             = yes
```

### 3. 第 21 步：常压长程平衡 (`21npt.mdp`)
```ini
integrator               = md
nsteps                   = 800000       ; 800 ps
dt                       = 0.001

tcoupl                   = v-rescale
tc-grps                  = system
tau_t                    = 0.1
ref_t                    = 298

pcoupl                   = Parrinello-Rahman  ; 正式平衡使用 Parrinello-Rahman
pcoupltype               = isotropic
tau_p                    = 5.0
ref_p                    = 1.0          ; 1 bar 常压

gen_vel                  = no
continuation             = yes
```
