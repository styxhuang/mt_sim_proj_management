import pandas as pd
import matplotlib.pyplot as plt
import os

def plot_md_complete_analysis():
    all_density = []
    all_energy = []
    current_time_offset = 0.0  # 累计总时长 (ps)
    stage_boundaries = [0.0]   # 分隔线位置 (ps)

    # 1. 循环读取阶段数据
    for i in range(1, 30):
        e_file = f"{i}energy.xvg"
        d_file = f"{i}density.xvg"
        
        # 以能量文件作为该阶段存在及时间的基准
        if os.path.exists(e_file):
            # 读取能量 (跳过注释)
            e_data = pd.read_csv(e_file, sep=r'\s+', comment='@', header=None, names=['Time', 'Val'])
            e_data = e_data.dropna()
            
            # 计算该阶段内的时间跨度 (ps)
            duration_ps = e_data['Time'].iloc[-1] - e_data['Time'].iloc[0]
            
            # 统一时间轴：(当前点 - 阶段起点) + 累计偏移
            e_data['GlobalTime'] = (e_data['Time'] - e_data['Time'].iloc[0]) + current_time_offset
            e_data.attrs['stage'] = i  # 打上阶段标签
            all_energy.append(e_data)
            
            # 读取密度 (如果存在)
            if os.path.exists(d_file) and os.path.getsize(d_file) > 0:
                d_data = pd.read_csv(d_file, sep=r'\s+', comment='@', header=None, names=['Time', 'Val'])
                d_data = d_data.dropna()
                d_data['GlobalTime'] = (d_data['Time'] - d_data['Time'].iloc[0]) + current_time_offset
                d_data.attrs['stage'] = i
                all_density.append(d_data)
            
            # 更新下一阶段的起始偏移量
            current_time_offset += duration_ps
            stage_boundaries.append(current_time_offset)

    if not all_energy:
        print("未找到任何能量数据文件 (*energy.xvg)。")
        return

    # 找到最后阶段的标号
    last_stage_e = max([df.attrs.get('stage') for df in all_energy]) if all_energy else None
    last_stage_d = max([df.attrs.get('stage') for df in all_density]) if all_density else None

    # 2. 绘图设置
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

    # --- 绘制密度子图 (Top) ---
    if all_density:
        for df in all_density:
            # 所有原始数据用浅蓝色细线
            ax1.plot(df['GlobalTime'], df['Val']/1000, color='#3498db', alpha=0.3, linewidth=0.8)
            
            # 针对最后阶段进行分析
            if df.attrs.get('stage') == last_stage_d:
                # 50个采样点窗口的平均线
                ma_dens = (df['Val']/1000).rolling(window=50, center=True).mean()
                ax1.plot(df['GlobalTime'], ma_dens, color='#1b4f72', linewidth=2.5, label=f'Stage {last_stage_d} 50-pt Avg')
                
                # 计算最后 500 ps 的平均密度
                last_500_mask = df['Time'] >= (df['Time'].iloc[-1] - 500)
                if last_500_mask.any():
                    mean_dens_last500 = (df[last_500_mask]['Val'] / 1000).mean()
                    start_time_last500 = df[last_500_mask]['GlobalTime'].iloc[0]
                    end_time_last500 = df['GlobalTime'].iloc[-1]
                    # 在最后 500ps 范围内绘制横线，并在图例中标注数值
                    ax1.hlines(mean_dens_last500, start_time_last500, end_time_last500, 
                               color='red', linestyle='--', linewidth=2.5, 
                               label=f'Last 500ps Avg: {mean_dens_last500:.4f} g/cm$^3$')

    # --- 绘制能量子图 (Bottom) ---
    if all_energy:
        # 合并所有能量数据用于背景绘制
        df_ener_total = pd.concat(all_energy)
        ax2.plot(df_ener_total['GlobalTime'], df_ener_total['Val'], color='#e74c3c', alpha=0.3, linewidth=0.8)
        
        # 寻找最后阶段能量绘制平均线
        s_last_ener_list = [df for df in all_energy if df.attrs.get('stage') == last_stage_e]
        if s_last_ener_list:
            s_last_e = s_last_ener_list[0]
            ma_ener = s_last_e['Val'].rolling(window=50, center=True).mean()
            ax2.plot(s_last_e['GlobalTime'], ma_ener, color='#7b241c', linewidth=2.5, label=f'Stage {last_stage_e} 50-pt Avg')
            
            # 计算最后 500 ps 的平均能量
            last_500_mask = s_last_e['Time'] >= (s_last_e['Time'].iloc[-1] - 500)
            if last_500_mask.any():
                mean_ener_last500 = s_last_e[last_500_mask]['Val'].mean()
                start_time_last500 = s_last_e[last_500_mask]['GlobalTime'].iloc[0]
                end_time_last500 = s_last_e['GlobalTime'].iloc[-1]
                # 在最后 500ps 范围内绘制横线，并在图例中标注数值
                ax2.hlines(mean_ener_last500, start_time_last500, end_time_last500, 
                           color='blue', linestyle='--', linewidth=2.5, 
                           label=f'Last 500ps Avg: {mean_ener_last500:.1f} kJ/mol')

    # --- 阶段分隔虚线 (去掉文本标签) ---
    for b in stage_boundaries[:-1]:
        ax1.axvline(x=b, color='black', linestyle='--', alpha=0.2, linewidth=1)
        ax2.axvline(x=b, color='black', linestyle='--', alpha=0.2, linewidth=1)

    # 装饰图表
    ax1.set_ylabel('Density ($g/cm^3$)', fontsize=12)
    ax1.set_title('Multistage Simulation Equilibration Analysis', fontsize=14)
    ax1.legend(loc='lower right')
    ax1.grid(True, axis='y', alpha=0.1)

    ax2.set_ylabel('Total Energy ($kJ/mol$)', fontsize=12)
    ax2.set_xlabel('Total Cumulative Time (ps)', fontsize=12)
    ax2.legend(loc='lower right')
    ax2.grid(True, axis='y', alpha=0.1)

    plt.tight_layout()
    plt.savefig('energy-density.png', dpi=300)
    print(f"分析完成！总模拟时长: {current_time_offset:.2f} ps。图表已保存为 energy-density.png")

# 执行
if __name__ == "__main__":
    plot_md_complete_analysis()
