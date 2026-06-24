import os

def create_mdp(filename, nsteps, dt, temp, pcoupl, press, tau_p=2.0, gen_vel=False):
    mdp_content = f"""integrator               = md
nsteps                   = {nsteps}
dt                       = {dt}

nstxout                  = 0
nstvout                  = 0
nstfout                  = 0
nstlog                   = 1000
nstenergy                = 1000
nstcalcenergy            = 100

cutoff-scheme            = Verlet
rlist                    = 1.0
coulombtype              = PME
rcoulomb                 = 1.0
rvdw                     = 1.0
DispCorr                 = EnerPres

tcoupl                   = v-rescale
tc-grps                  = system
tau_t                    = 0.1
ref_t                    = {temp}
"""

    if gen_vel:
        mdp_content += f"""
gen_vel                  = yes
gen_temp                 = {temp}
gen_seed                 = -1
continuation             = no
"""
    else:
        mdp_content += f"""
gen_vel                  = no
continuation             = yes
"""

    if pcoupl != "no":
        # For last step, use Parrinello-Rahman, else Berendsen/C-rescale
        pcoupl_type = "Parrinello-Rahman" if "parrinello" in pcoupl.lower() else "Berendsen"
        mdp_content += f"""
pcoupl                   = {pcoupl_type}
pcoupltype               = isotropic
tau_p                    = {tau_p}
ref_p                    = {press}
compressibility          = 4.5e-5
"""
    else:
        mdp_content += """
pcoupl                   = no
"""

    mdp_content += """
constraint_algorithm     = lincs
constraints              = h-bonds
lincs_iter               = 1
lincs_order              = 4

pbc                      = xyz
"""
    with open(filename, 'w') as f:
        f.write(mdp_content)
    print(f"Generated {filename}")

def create_em_mdp(filename, nsteps=50000):
    mdp_content = f"""integrator               = steep
nsteps                   = {nsteps}
emtol                    = 100.0
emstep                   = 0.01

nstxout                  = 0
nstvout                  = 0
nstfout                  = 0
nstlog                   = 1000
nstenergy                = 100

cutoff-scheme            = Verlet
rlist                    = 1.0
coulombtype              = PME
rcoulomb                 = 1.0
rvdw                     = 1.0
DispCorr                 = EnerPres

pbc                      = xyz
"""
    with open(filename, 'w') as f:
        f.write(mdp_content)
    print(f"Generated {filename}")

def main():
    os.makedirs("mdp", exist_ok=True)
    
    # Generate Energy Minimization steps
    create_em_mdp("mdp/em.mdp", 50000)
    create_em_mdp("mdp/em2.mdp", 50000)
    
    # Define protocol (Step, Ensemble, Temp, Press, Duration_ps, dt)
    # nsteps = Duration_ps / dt
    protocol = [
        (1,  "NVT", 600, None, 50,  0.001),
        (2,  "NVT", 300, None, 100, 0.001),
        (3,  "NPT", 300, 1000, 50,  0.001),
        
        (4,  "NVT", 600, None, 50,  0.001),
        (5,  "NVT", 300, None, 100, 0.001),
        (6,  "NPT", 300, 30000,50,  0.001),
        
        (7,  "NVT", 600, None, 50,  0.001),
        (8,  "NVT", 300, None, 100, 0.001),
        (9,  "NPT", 300, 50000,50,  0.001),
        
        (10, "NVT", 600, None, 50,  0.001),
        (11, "NVT", 300, None, 100, 0.001),
        (12, "NPT", 300, 25000,50,  0.001),
        
        (13, "NVT", 600, None, 50,  0.001),
        (14, "NVT", 300, None, 100, 0.001),
        (15, "NPT", 300, 5000, 50,  0.001),
        
        (16, "NVT", 600, None, 50,  0.001),
        (17, "NVT", 300, None, 100, 0.001),
        (18, "NPT", 300, 500,  50,  0.001),
        
        (19, "NVT", 600, None, 50,  0.001),
        (20, "NVT", 300, None, 100, 0.001),
        (21, "NPT", 298, 1,    800, 0.001),
    ]
    
    for step, ens, temp, press, dur, dt in protocol:
        nsteps = int(dur / dt)
        filename = f"mdp/{step}{ens.lower()}.mdp"
        gen_vel = (step == 1)
        pcoupl = "no" if ens == "NVT" else ("parrinello-rahman" if step == 21 else "berendsen")
        
        create_mdp(filename, nsteps, dt, temp, pcoupl, press, tau_p=2.0 if step!=21 else 5.0, gen_vel=gen_vel)
        
if __name__ == "__main__":
    main()
