# main.py (修复版)
import asyncio
import time

# 根据可用的工具选择管理器
try:
    from anvil_manager import AnvilManager as NodeManager
    print("Using Anvil Manager")
except ImportError:
    try:
        from ganache_manager import GanacheManager as NodeManager
        print("Using Ganache Manager")
    except ImportError:
        print("No blockchain node manager available")
        exit(1)

from trading_simulator import RealtimeTradingSimulator
from monitor import RealtimeMonitor

async def main():
    # 启动节点，增加初始余额
    node_manager = NodeManager(port=8545, accounts=50)  # 减少账户数量
    if not node_manager.start(block_time=2):  # 增加出块时间
        print("Failed to start blockchain node")
        return
    
    try:
        # 创建模拟器
        simulator = RealtimeTradingSimulator(node_manager, max_workers=10)
        simulator.initialize()
        
        # 等待一下让节点稳定
        await asyncio.sleep(3)
        
        # 创建监控器
        monitor = RealtimeMonitor(simulator)
        simulator.on_transaction_complete = monitor.on_transaction_complete
        
        # 开始监控
        monitor.start_monitoring(interval=2.0)
        
        print("开始实时交易模拟...")
        
        # 场景1: 保守的随机交易
        print("\n=== 场景1: 保守随机交易模拟 ===")
        await simulator.simulate_random_trading(
            transactions_per_second=5,   # 降低TPS
            duration_seconds=30,
            min_amount=0.001,           # 最小0.001 ETH
            max_amount=0.1              # 最大0.1 ETH
        )
        
        # 等待一下
        await asyncio.sleep(5)
        
        # 显示余额状态
        print("\n=== 账户余额状态 ===")
        for i in range(min(5, len(simulator.accounts))):
            balance = simulator.get_balance(i)
            balance_eth = simulator.w3.from_wei(balance, 'ether')
            print(f"账户 {i}: {balance_eth:.4f} ETH")
        
        # 场景2: 小额高频交易
        print("\n\n=== 场景2: 小额高频交易 ===")
        await simulator.simulate_random_trading(
            transactions_per_second=20,  # 中等TPS
            duration_seconds=20,
            min_amount=0.0001,          # 非常小的金额
            max_amount=0.01             # 小金额
        )
        
        # 停止监控
        monitor.stop_monitoring()
        
        # 显示最终统计
        print("\n\n=== 最终统计 ===")
        final_stats = simulator.get_performance_stats()
        for key, value in final_stats.items():
            if isinstance(value, float):
                print(f"{key}: {value:.4f}")
            else:
                print(f"{key}: {value}")
        
        # 导出结果
        monitor.export_results("simulation_results.json")
        print("\n结果已导出到 simulation_results.json")
        
    finally:
        # 停止节点
        node_manager.stop()

if __name__ == "__main__":
    asyncio.run(main())