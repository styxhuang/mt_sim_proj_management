---
name: build_amorphous
description: Build amorphous multi-component molecular systems from prebuilt monomer structures, molar ratios, and target atom counts. Use when assembling full simulation boxes, polymer blends, resin systems, liquids, or mixed molecular systems; not for generating a single molecule SMILES.
---

# Build Amorphous System

## Purpose

`build_amorphous` assembles a full amorphous molecular system from already-built component structures.

Use this skill after `build_molecule` has produced reliable single-component structures. It should never ask the model to invent a single SMILES for a multi-component mixture.

## Inputs

- Component structures: PDB content for each molecule, ion, polymer repeat unit, or representative component.
- Component identity: the ASCII three-character `buildingBlocks[].code` value from the modeling spec.
- Composition: `targetSystem.components[].count`, interpreted as molar ratio or explicit count depending on whether a target atom count is provided.
- Target size: `targetSystem.atomCount` or a target atom count written in `targetSystem.box`.

## Behavior

1. Match each `targetSystem.components[].block` to a built component structure by its three-character code.
2. Convert molar ratios to integer molecule counts when a target atom count is present.
3. Preserve each molecule's internal geometry.
4. Randomly place and rotate molecule copies in a large initial box.
5. Avoid severe overlaps using distance checks.
6. Return one assembled `system.pdb`.

## Output

- Full-system PDB structure.
- PDB residue names must be ASCII three-character component codes only. Never use Chinese residue names.
- Component count summary, for example:
  - `ECO×250`
  - `MTH×200`
  - `DMP×40`

## Rules

- Do not encode a full mixture as one dot-separated SMILES string.
- Do not create covalent bonds between components unless the modeling spec explicitly asks for a reacted network model.
- Do not call `build_molecule` for requests about increasing full-system molecule count, target atom count, density, molar ratio, or box-scale assembly.
- For full-system requests, reuse existing component structures and re-run amorphous assembly.
- Reject or rewrite any Chinese component label before writing PDB; use a deterministic ASCII three-character fallback such as `M01` only when no code is available.
