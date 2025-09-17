# main.py
import asyncio
import time
from anvil_manager import AnvilManager
from trading_simulator import RealtimeTradingSimulator
from monitor import RealtimeMonitor

async def main():
    # 启动Anvil
    anvil = AnvilManager(port=8545, accounts=100)
    if not anvil.start(block_time=1):
        print("Failed to start Anvil")
        return
    
    try:
        # 创建模拟器
        simulator = RealtimeTradingSimulator(anvil, max_workers=20)
        simulator.initialize()
        
        # 创建监控器
        monitor = RealtimeMonitor(simulator)
        simulator.on_transaction_complete = monitor.on_transaction_complete
        
        # 开始监控
        monitor.start_monitoring(interval=1.0)
        
        print("开始实时交易模拟...")
        
        # 场景1: 持续随机交易
        print("\n=== 场景1: 随机交易模拟 ===")
        await simulator.simulate_random_trading(
            transactions_per_second=50,  # 50 TPS
            duration_seconds=30,         # 持续30秒
            min_amount=0.01,
            max_amount=1.0
        )
        
        # 等待一下
        await asyncio.sleep(2)
        
        # 场景2: 高频批量交易
        print("\n\n=== 场景2: 高频批量交易 ===")
        simulator.simulate_high_frequency_trading(
            batch_size=200,              # 每批200笔交易
            batches=5,                   # 5批
            delay_between_batches=2.0    # 批次间隔2秒
        )
        
        # 停止监控
        monitor.stop_monitoring()
        
        # 显示最终统计
        print("\n\n=== 最终统计 ===")
        final_stats = simulator.get_performance_stats()
        for key, value in final_stats.items():
            print(f"{key}: {value}")
        
        # 导出结果
        monitor.export_results("simulation_results.json")
        print("\n结果已导出到 simulation_results.json")
        
    finally:
        # 停止Anvil
        anvil.stop()

if __name__ == "__main__":
    asyncio.run(main())