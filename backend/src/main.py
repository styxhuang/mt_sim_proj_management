"""后端入口（瘦封装）。

实际实现位于 :mod:`sim_backend` 包。保留此文件是为了让现有启动脚本
（``python3 src/main.py``）继续可用。
"""

from sim_backend.server import main

if __name__ == "__main__":
    main()
