"""化学结构生成工具。

大模型直接输出 3D 坐标很不可靠（氢原子常飘到键合不上的位置）。因此：
- 单分子：让模型只给 SMILES，由 RDKit 加氢、ETKDG 嵌入并 MMFF 优化，得到几何合理的 3D 结构（PDB）。
- 体系组装：复用已建好的单体 PDB，按确定性网格平移摆放（不破坏分子内部几何），避免再次出现飘原子。

RDKit 不可用时各函数返回 ``None``，调用方应回退到模型输出的结构块。
"""

from __future__ import annotations

import math
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:  # RDKit 可选依赖
    from rdkit import Chem
    from rdkit.Chem import AllChem

    _RDKIT_OK = True
except Exception:  # pragma: no cover - 环境无 RDKit 时
    _RDKIT_OK = False


_PACKMOL_CANDIDATES = (
    "/opt/mamba/envs/structure_build/bin/packmol",
    "/opt/conda/envs/structure_build/bin/packmol",
)


def rdkit_available() -> bool:
    return _RDKIT_OK


def _find_packmol() -> str | None:
    found = shutil.which("packmol")
    if found:
        return found
    for candidate in _PACKMOL_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def smiles_to_pdb(smiles: str, seed: int = 0xF00D) -> str | None:
    """SMILES → 加氢、3D 嵌入并 MMFF 优化后的 PDB 文本；失败返回 ``None``。"""
    if not _RDKIT_OK:
        return None
    smiles = str(smiles or "").strip()
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(mol, params) != 0:
        if AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=seed) != 0:
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception:  # 优化失败不致命，保留嵌入坐标
        pass
    pdb = Chem.MolToPDBBlock(mol)
    return pdb or None


# --- 体系组装：确定性网格摆放（纯文本 PDB 处理，不依赖 RDKit 重新解析） ---

def _parse_pdb_atoms(content: str) -> list[dict]:
    atoms: list[dict] = []
    for line in str(content or "").splitlines():
        record = line[:6].strip()
        if record not in ("ATOM", "HETATM"):
            continue
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (ValueError, IndexError):
            continue
        name = line[12:16].strip() or "X"
        resname = line[17:20].strip() or "LIG"
        element = (line[76:78].strip() if len(line) >= 78 else "") or _guess_element(name)
        atoms.append({"name": name, "resname": resname, "element": element, "x": x, "y": y, "z": z})
    return atoms


def _guess_element(name: str) -> str:
    letters = "".join(ch for ch in name if ch.isalpha())
    if not letters:
        return "C"
    if len(letters) >= 2 and letters[1].islower():
        return letters[0].upper() + letters[1].lower()
    return letters[0].upper()


def _centroid(atoms: list[dict]) -> tuple[float, float, float]:
    n = len(atoms)
    return (
        sum(a["x"] for a in atoms) / n,
        sum(a["y"] for a in atoms) / n,
        sum(a["z"] for a in atoms) / n,
    )


def _bbox_dim(atoms: list[dict]) -> float:
    xs = [a["x"] for a in atoms]
    ys = [a["y"] for a in atoms]
    zs = [a["z"] for a in atoms]
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)


def _chain_id(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return alphabet[index % len(alphabet)]


def _format_atom(serial: int, name: str, resname: str, chain: str, resseq: int,
                 x: float, y: float, z: float, element: str) -> str:
    if len(name) >= 4:
        nm = name[:4]
    else:
        nm = " " + name.ljust(3)
    resseq = resseq % 10000
    return (
        "HETATM"
        f"{serial % 100000:>5}"
        " "
        f"{nm}"
        " "
        f"{resname[:3]:>3}"
        " "
        f"{chain:1}"
        f"{resseq:>4}"
        " "
        "   "
        f"{x:8.3f}{y:8.3f}{z:8.3f}"
        "  1.00  0.00"
        "          "
        f"{element:>2}"
    )


def _component_resname(name: str, index: int) -> str:
    raw = str(name or "").strip().upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", raw)
    if cleaned and cleaned[0].isalpha():
        return cleaned[:3].ljust(3, "X")
    return f"M{(index + 1) % 100:02d}"


def _pdb_with_resname(atoms: list[dict], resname: str) -> str:
    lines = [
        _format_atom(index, atom["name"], resname, "A", 1, atom["x"], atom["y"], atom["z"], atom["element"])
        for index, atom in enumerate(atoms, start=1)
    ]
    lines.append("END")
    return "\n".join(lines) + "\n"


def _rand_rotation(rng: random.Random) -> tuple[float, ...]:
    """均匀随机旋转矩阵（按 Shoemake 四元数法），返回行主序 9 元组。"""
    u1, u2, u3 = rng.random(), rng.random(), rng.random()
    a, b = math.sqrt(1.0 - u1), math.sqrt(u1)
    x = a * math.sin(2 * math.pi * u2)
    y = a * math.cos(2 * math.pi * u2)
    z = b * math.sin(2 * math.pi * u3)
    w = b * math.cos(2 * math.pi * u3)
    return (
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
    )


def pack_pdbs(
    components: list[dict],
    min_dist: float = 2.0,
    packing_fraction: float = 0.18,
    seed: int = 20260621,
    max_attempts: int = 400,
) -> str | None:
    """用 Packmol 把若干单体 PDB 填充进一个立方盒，组装成无定形体系 PDB。

    组件按输入顺序写入 Packmol ``structure`` 块，因此输出 PDB 的分子类别顺序
    与组件顺序一致，便于 GROMACS ``[ molecules ]`` 使用紧凑分组。Packmol 缺失或
    失败时直接返回 ``None``，不回退到自写 packer。

    ``components``：``[{"content": pdb, "count": int, "name": str}]``。失败返回 ``None``。
    """
    packmol = _find_packmol()
    if not packmol:
        return None

    parsed: list[tuple[list[dict], int, str]] = []
    for index, comp in enumerate(components or []):
        atoms = _parse_pdb_atoms(comp.get("content", ""))
        if not atoms:
            continue
        try:
            count = int(comp.get("count"))
        except (TypeError, ValueError):
            count = 1
        count = max(1, min(count, 50000))
        parsed.append((atoms, count, _component_resname(str(comp.get("name", "LIG")), index)))
    if not parsed:
        return None

    # 估算盒子边长：取两个下界的较大者——
    # 1) 分子包围球体积之和 / 堆积分数；
    # 2) 原子数 × min_dist³ × 松弛系数（保证原子级最小间距有足够空间，避免被迫重叠）。
    # 规划要求“低密度随机填充”，因此偏向宽松。
    total_vol = 0.0
    max_dim = 1.0
    total_atoms = 0
    for atoms, count, _ in parsed:
        dim = _bbox_dim(atoms)
        max_dim = max(max_dim, dim)
        radius = 0.5 * dim
        total_vol += (4.0 / 3.0) * math.pi * radius ** 3 * count
        total_atoms += len(atoms) * count
    vol_by_molecules = total_vol / packing_fraction
    vol_by_atoms = total_atoms * (min_dist ** 3) * 2.5
    side = max(vol_by_molecules, vol_by_atoms) ** (1.0 / 3.0)
    side = max(side, max_dim * 1.8)

    with tempfile.TemporaryDirectory(prefix="sim_packmol_") as tmp:
        tmp_path = Path(tmp)
        output_path = tmp_path / "system.pdb"
        input_lines = [
            f"tolerance {max(float(min_dist), 0.1):.3f}",
            "filetype pdb",
            f"output {output_path}",
            f"seed {int(seed)}",
        ]
        for index, (atoms, count, resname) in enumerate(parsed, start=1):
            component_path = tmp_path / f"component_{index}_{resname}.pdb"
            component_path.write_text(_pdb_with_resname(atoms, resname), encoding="utf-8")
            input_lines.extend(
                [
                    f"structure {component_path}",
                    f"  number {count}",
                    f"  inside box 0. 0. 0. {side:.3f} {side:.3f} {side:.3f}",
                    "end structure",
                ]
            )
        packmol_input = "\n".join(input_lines) + "\n"
        input_path = tmp_path / "packmol.inp"
        input_path.write_text(packmol_input, encoding="utf-8")
        try:
            with input_path.open(encoding="utf-8") as stdin:
                completed = subprocess.run(
                    [packmol],
                    stdin=stdin,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0 or not output_path.exists():
            return None
        packed = output_path.read_text(encoding="utf-8", errors="replace").strip()
        if not packed:
            return None
        cryst = f"CRYST1{side:9.3f}{side:9.3f}{side:9.3f}  90.00  90.00  90.00 P 1           1"
        lines = packed.splitlines()
        if not any(line.startswith("CRYST1") for line in lines[:3]):
            lines.insert(0, cryst)
        if not lines[-1].startswith("END"):
            lines.append("END")
        return "\n".join(lines)
