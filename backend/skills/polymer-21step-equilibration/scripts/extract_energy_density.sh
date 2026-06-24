#!/bin/bash

# 判断 gmx 命令前缀
GMX_CMD="gmx"
if command -v gmx_mpi >/dev/null 2>&1; then
    GMX_CMD="gmx_mpi"
fi

for i in {1..30}; do
    # 自动识别文件名
    if [ -f "${i}npt.edr" ]; then
        INFILE="${i}npt.edr"
    elif [ -f "${i}nvt.edr" ]; then
        INFILE="${i}nvt.edr"
    else
        continue
    fi

    echo "Processing $INFILE ..."
    
    # 提取总能量 (每个阶段都有)
    echo "Total-Energy" | $GMX_CMD energy -f $INFILE -o ${i}energy.xvg -xvg none
    
    # 提取密度 (尝试提取，如果失败不报错)
    echo "Density" | $GMX_CMD energy -f $INFILE -o ${i}density.xvg -xvg none || echo "No density in $INFILE"
done
