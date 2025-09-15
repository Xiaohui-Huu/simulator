#!/usr/bin/env python3
"""
以太坊交易模拟器安装脚本
"""

import subprocess
import sys
import os

def check_foundry():
    """检查Foundry是否已安装"""
    try:
        result = subprocess.run(['forge', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Foundry已安装")
            print(f"版本: {result.stdout.strip()}")
            return True
        else:
            print("❌ Foundry未安装")
            return False
    except FileNotFoundError:
        print("❌ Foundry未安装")
        return False

def install_foundry():
    """安装Foundry"""
    print("🔧 开始安装Foundry...")
    
    if os.name == 'nt':  # Windows
        print("请手动安装Foundry:")
        print("1. 访问 https://getfoundry.sh/")
        print("2. 按照说明安装Foundry")
        print("3. 重新运行此脚本")
        return False
    else:  # Unix-like systems
        try:
            # 下载并安装foundryup
            subprocess.run(['curl', '-L', 'https://foundry.paradigm.xyz', '|', 'bash'], 
                         shell=True, check=True)
            
            # 运行foundryup
            subprocess.run(['foundryup'], check=True)
            
            print("✅ Foundry安装完成")
            return True
        except subprocess.CalledProcessError:
            print("❌ Foundry安装失败")
            return False

def install_python_deps():
    """安装Python依赖"""
    print("📦 安装Python依赖...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                      check=True)
        print("✅ Python依赖安装完成")
        return True
    except subprocess.CalledProcessError:
        print("❌ Python依赖安装失败")
        return False

def main():
    print("🚀 以太坊交易模拟器安装程序")
    print("="*40)
    
    # 检查并安装Foundry
    if not check_foundry():
        if not install_foundry():
            print("❌ 请手动安装Foundry后重试")
            return
    
    # 安装Python依赖
    if not install_python_deps():
        print("❌ 安装失败")
        return
    
    print("\n✅ 安装完成!")
    print("\n使用方法:")
    print("python eth_simulator.py")

if __name__ == "__main__":
    main()