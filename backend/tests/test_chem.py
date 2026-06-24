import os
import re
import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sim_backend import chem  # noqa: E402


WATER_PDB = """\
HETATM    1  O   LIG A   1       0.000   0.000   0.000  1.00  0.00           O
HETATM    2  H1  LIG A   1       0.957   0.000   0.000  1.00  0.00           H
HETATM    3  H2  LIG A   1      -0.239   0.927   0.000  1.00  0.00           H
END
"""

METHANE_PDB = """\
HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C
HETATM    2  H1  LIG A   1       0.629   0.629   0.629  1.00  0.00           H
HETATM    3  H2  LIG A   1      -0.629  -0.629   0.629  1.00  0.00           H
HETATM    4  H3  LIG A   1      -0.629   0.629  -0.629  1.00  0.00           H
HETATM    5  H4  LIG A   1       0.629  -0.629  -0.629  1.00  0.00           H
END
"""


def fake_packmol_run(args, input=None, **kwargs):
    if input is None and kwargs.get("stdin") is not None:
        input = kwargs["stdin"].read()
    output_match = re.search(r"^output\s+(.+)$", input or "", re.MULTILINE)
    assert output_match
    output_path = output_match.group(1).strip()
    input_lines = (input or "").splitlines()
    blocks = []
    for index, line in enumerate(input_lines):
        if line.startswith("structure "):
            number = next(
                int(candidate.split()[1])
                for candidate in input_lines[index + 1 :]
                if candidate.strip().startswith("number ")
            )
            blocks.append((line.split(maxsplit=1)[1], number))
    lines = ["REMARK fake packmol output"]
    serial = 1
    resseq = 1
    for pdb_path, count_text in blocks:
        atoms = chem._parse_pdb_atoms(Path(pdb_path.strip()).read_text(encoding="utf-8"))
        for copy_index in range(int(count_text)):
            for atom in atoms:
                lines.append(
                    chem._format_atom(
                        serial,
                        atom["name"],
                        atom["resname"],
                        "A",
                        resseq,
                        atom["x"] + copy_index * 3.0,
                        atom["y"],
                        atom["z"],
                        atom["element"],
                    )
                )
                serial += 1
            resseq += 1
    lines.append("END")
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")


@unittest.skipUnless(chem.rdkit_available(), "RDKit not installed")
class SmilesToPdbTests(unittest.TestCase):
    def test_water_has_three_atoms_with_hydrogens(self) -> None:
        pdb = chem.smiles_to_pdb("O")
        self.assertIsNotNone(pdb)
        atoms = chem._parse_pdb_atoms(pdb)
        elements = sorted(a["element"] for a in atoms)
        self.assertEqual(elements, ["H", "H", "O"])

    def test_hydrogens_bonded_close_to_oxygen(self) -> None:
        pdb = chem.smiles_to_pdb("O")
        atoms = chem._parse_pdb_atoms(pdb)
        oxygen = next(a for a in atoms if a["element"] == "O")
        for hydrogen in (a for a in atoms if a["element"] == "H"):
            dist = (
                (hydrogen["x"] - oxygen["x"]) ** 2
                + (hydrogen["y"] - oxygen["y"]) ** 2
                + (hydrogen["z"] - oxygen["z"]) ** 2
            ) ** 0.5
            # 合理的 O-H 键长在 1 Å 附近，绝不会飘到几 Å 之外。
            self.assertLess(dist, 1.3)

    def test_invalid_smiles_returns_none(self) -> None:
        self.assertIsNone(chem.smiles_to_pdb("not-a-smiles!!!"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(chem.smiles_to_pdb(""))


@unittest.skipUnless(chem.rdkit_available(), "RDKit not installed")
class PackPdbsTests(unittest.TestCase):
    def test_packs_multiple_copies_into_single_pdb(self) -> None:
        with patch.object(chem, "_find_packmol", return_value="/usr/bin/packmol"), \
                patch.object(chem.subprocess, "run", side_effect=fake_packmol_run):
            packed = chem.pack_pdbs([{"content": WATER_PDB, "count": 4, "name": "水"}])
        self.assertIsNotNone(packed)
        atoms = chem._parse_pdb_atoms(packed)
        # 4 份水，每份 3 个原子。
        self.assertEqual(len(atoms), 12)
        self.assertEqual({atom["resname"] for atom in atoms}, {"M01"})

    def test_ascii_three_letter_component_name_is_preserved_as_residue_name(self) -> None:
        with patch.object(chem, "_find_packmol", return_value="/usr/bin/packmol"), \
                patch.object(chem.subprocess, "run", side_effect=fake_packmol_run):
            packed = chem.pack_pdbs([{"content": WATER_PDB, "count": 1, "name": "ECO"}])
        atoms = chem._parse_pdb_atoms(packed)
        self.assertEqual({atom["resname"] for atom in atoms}, {"ECO"})

    def test_packmol_output_keeps_component_order_grouped(self) -> None:
        with patch.object(chem, "_find_packmol", return_value="/usr/bin/packmol"), \
                patch.object(chem.subprocess, "run", side_effect=fake_packmol_run):
            packed = chem.pack_pdbs(
                [
                    {"content": WATER_PDB, "count": 2, "name": "ECO"},
                    {"content": METHANE_PDB, "count": 2, "name": "MTH"},
                ]
            )
        atoms = chem._parse_pdb_atoms(packed)
        molecule_resnames = [atoms[index]["resname"] for index in (0, 3, 6, 11)]
        self.assertEqual(molecule_resnames, ["ECO", "ECO", "MTH", "MTH"])

    def test_missing_packmol_returns_none_without_fallback(self) -> None:
        with patch.object(chem, "_find_packmol", return_value=None):
            self.assertIsNone(chem.pack_pdbs([{"content": WATER_PDB, "count": 1, "name": "ECO"}]))

    def test_copies_do_not_overlap(self) -> None:
        water = chem.smiles_to_pdb("O")
        with patch.object(chem, "_find_packmol", return_value="/usr/bin/packmol"), \
                patch.object(chem.subprocess, "run", side_effect=fake_packmol_run):
            packed = chem.pack_pdbs([{"content": water, "count": 2, "name": "水"}], min_dist=2.0)
        atoms = chem._parse_pdb_atoms(packed)
        self.assertEqual(len([a for a in atoms if a["element"] == "O"]), 2)
        # 任意跨分子原子对都应满足最小间距（取最近原子对验证）。
        nearest = min(
            ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2) ** 0.5
            for i, a in enumerate(atoms)
            for b in atoms[i + 1:]
        )
        self.assertGreater(nearest, 0.7)

    def test_two_species_are_grouped_by_component_order(self) -> None:
        water = chem.smiles_to_pdb("O")
        methane = chem.smiles_to_pdb("C")
        with patch.object(chem, "_find_packmol", return_value="/usr/bin/packmol"), \
                patch.object(chem.subprocess, "run", side_effect=fake_packmol_run):
            packed = chem.pack_pdbs(
                [
                    {"content": water, "count": 6, "name": "水"},
                    {"content": methane, "count": 6, "name": "甲烷"},
                ]
            )
        self.assertIsNotNone(packed)
        atoms = chem._parse_pdb_atoms(packed)
        # 两种分子都在，且数量正确（水 3 原子×6，甲烷 5 原子×6）。
        self.assertEqual(len(atoms), 6 * 3 + 6 * 5)
        self.assertEqual([atoms[index]["resname"] for index in (0, 15, 18, 43)], ["M01", "M01", "M02", "M02"])

    def test_empty_components_returns_none(self) -> None:
        self.assertIsNone(chem.pack_pdbs([]))


if __name__ == "__main__":
    unittest.main()
