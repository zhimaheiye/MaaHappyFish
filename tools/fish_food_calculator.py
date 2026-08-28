# -*- coding: utf-8 -*-
"""
开心水族箱 - 挂机鱼食需求计算器
"""

import math
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta

def calculate():
    try:
        # 参数 1：海星容量 (粒/单位)
        capacity_str = entry_capacity.get().strip()
        if not capacity_str:
            messagebox.showwarning("提示", "请输入海星容量上限！")
            return
        capacity = float(capacity_str)

        # 参数 2：当前存粮预计可用时长 (分钟)
        current_minutes_str = entry_current_duration.get().strip()
        if not current_minutes_str:
            messagebox.showwarning("提示", "请输入当前预计可用时长！")
            return
        current_minutes = float(current_minutes_str)

        # 参数 3：打算挂机到几点 (0-23 整点)
        target_hour_str = entry_target_hour.get().strip()
        if not target_hour_str:
            messagebox.showwarning("提示", "请输入目标挂机整点时间（0-23）！")
            return
        target_hour = int(target_hour_str)
        if target_hour < 0 or target_hour > 23:
            messagebox.showwarning("提示", "整点时间必须在 0 到 23 之间！")
            return

        now = datetime.now()
        # 目标时间计算
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)

        diff_seconds = (target_time - now).total_seconds()
        total_hanging_minutes = diff_seconds / 60.0
        total_hanging_hours = total_hanging_minutes / 60.0

        # 计算消耗速率 (粒/分钟)
        if current_minutes <= 0:
            rate_per_min = 0
            needed_food = 0
            extra_minutes = total_hanging_minutes
        else:
            rate_per_min = capacity / current_minutes
            extra_minutes = max(0.0, total_hanging_minutes - current_minutes)
            needed_food = int(round(extra_minutes * rate_per_min + 0.4999)) # 向上取整

        needed_bags = math.ceil(needed_food / 30.0)

        # 格式化输出
        res_text = (
            f"【挂机规划结果】\n"
            f"----------------------------------------\n"
            f"• 当前时间：{now.strftime('%H:%M')}\n"
            f"• 目标时间：{target_time.strftime('%m-%d %H:%M')}\n"
            f"• 总挂机时长：{total_hanging_hours:.1f} 小时 ({int(total_hanging_minutes)} 分钟)\n"
            f"• 当前海星可用：{int(current_minutes)} 分钟\n"
            f"• 缺口时长：{max(0, int(extra_minutes))} 分钟\n"
            f"----------------------------------------\n"
            f"👉 至少需额外准备鱼食：【 {needed_food} 粒 】\n"
            f"📦 折合需要购买：【 {needed_bags} 袋 】 (30粒/袋，已向上取整)\n"
            f"----------------------------------------\n"
            f"💡 建议：由于自动喂食有少许时间误差，建议多买 1 袋备用！"
        )
        label_result.config(text=res_text, fg="#1e3a8a")

    except ValueError:
        messagebox.showerror("错误", "请输入有效的数字！")

root = tk.Tk()
root.title("开心水族箱 - 挂机鱼食计算器")
root.geometry("480x560")
root.resizable(False, False)

# 标题
title_lbl = tk.Label(root, text="🐟 萌海星挂机鱼食需求计算器", font=("Microsoft YaHei", 14, "bold"), pady=10)
title_lbl.pack()

frame = tk.Frame(root, padx=20, pady=10)
frame.pack(fill="both", expand=True)

# 参数1
tk.Label(frame, text="1. 海星每次最大容量 (粒/单位):", font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky="w", pady=6)
entry_capacity = tk.Entry(frame, font=("Microsoft YaHei", 10), width=15)
entry_capacity.insert(0, "100")
entry_capacity.grid(row=0, column=1, pady=6, padx=10)

# 参数2
tk.Label(frame, text="2. 海星当前满粮/现有可喂时长 (分钟):", font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky="w", pady=6)
entry_current_duration = tk.Entry(frame, font=("Microsoft YaHei", 10), width=15)
entry_current_duration.insert(0, "120")
entry_current_duration.grid(row=1, column=1, pady=6, padx=10)

# 参数3
tk.Label(frame, text="3. 计划挂机到几点 (0-23 整点):", font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky="w", pady=6)
entry_target_hour = tk.Entry(frame, font=("Microsoft YaHei", 10), width=15)
entry_target_hour.insert(0, "8")
entry_target_hour.grid(row=2, column=1, pady=6, padx=10)

# 计算按钮
btn_calc = tk.Button(frame, text="🚀 开始计算所需鱼食量", font=("Microsoft YaHei", 11, "bold"), bg="#3b82f6", fg="white", padx=10, pady=5, command=calculate)
btn_calc.grid(row=3, column=0, columnspan=2, pady=15)

# 结果显示框
label_result = tk.Label(frame, text="请输入参数后点击上方按钮进行计算...", font=("Consolas", 10), justify="left", bg="#f3f4f6", padx=10, pady=10, relief="groove")
label_result.grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)

if __name__ == "__main__":
    root.mainloop()