import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
# 切换到项目根目录,确保所有相对路径(如 config/)可解析
os.chdir(BASE_DIR)

from core.app import main

if __name__ == "__main__":
    main()
