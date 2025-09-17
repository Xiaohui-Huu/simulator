# advanced_features.py
import random
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class TradingStrategy:
    name: str
    min_amount: float
    max_amount: float
    frequency: float  # transactions per second
    account_pool: List[int]  # 使用的账户索引

class AdvancedTradingSimulator(RealtimeTradingSimulator):
    def __init__(self, anvil_manager, max_workers: int = 10):
        super().__init__(anvil_manager, max_workers)
        self.strategies: List[TradingStrategy] = []
    
    def add_strategy(self, strategy: TradingStrategy):
        """添加交易策略"""
        self.strategies.append(strategy)
    
    async def simulate_multi_strategy(self, duration_seconds: int = 60):
        """多策略并行模拟"""
        tasks = []
        
        for strategy in self.strategies:
            task = asyncio.create_task(
                self._run_strategy(strategy, duration_seconds)
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
    
    async def _run_strategy(self, strategy: TradingStrategy, duration: int):
        """运行单个策略"""
        end_time = time.time() + duration
        interval = 1.0 / strategy.frequency
        
        while time.time() < end_time and self.running:
            from_idx = random.choice(strategy.account_pool)
            to_idx = random.choice(strategy.account_pool)
            
            while to_idx == from_idx:
                to_idx = random.choice(strategy.account_pool)
            
            amount = random.uniform(strategy.min_amount, strategy.max_amount)
            
            await self.send_transaction_async(from_idx, to_idx, amount)
            await asyncio.sleep(interval)

# 使用示例
def create_trading_strategies():
    return [
        TradingStrategy(
            name="高频小额",
            min_amount=0.001,
            max_amount=0.01,
            frequency=100,  # 100 TPS
            account_pool=list(range(0, 20))
        ),
        TradingStrategy(
            name="中频中额",
            min_amount=0.1,
            max_amount=1.0,
            frequency=20,   # 20 TPS
            account_pool=list(range(20, 40))
        ),
        TradingStrategy(
            name="低频大额",
            min_amount=1.0,
            max_amount=10.0,
            frequency=5,    # 5 TPS
            account_pool=list(range(40, 50))
        )
    ]