# trading_simulator.py
import asyncio
import time
import random
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

@dataclass
class TransactionResult:
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    gas_used: int
    status: bool
    timestamp: float
    block_number: int

class RealtimeTradingSimulator:
    def __init__(self, anvil_manager, max_workers: int = 10):
        self.anvil = anvil_manager
        self.w3 = Web3(Web3.HTTPProvider(anvil_manager.rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        self.accounts = []
        self.private_keys = []
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 统计信息
        self.stats = {
            'total_transactions': 0,
            'successful_transactions': 0,
            'failed_transactions': 0,
            'total_gas_used': 0,
            'start_time': 0
        }
        
        # 回调函数
        self.on_transaction_complete: Optional[Callable] = None
        self.running = False
        
    def initialize(self):
        """初始化账户和私钥"""
        # 获取Anvil预生成的账户
        accounts = self.anvil.get_accounts()
        self.accounts = accounts[:50]  # 使用前50个账户
        
        # 生成对应的私钥 (Anvil使用固定的助记词)
        # 这里简化处理，实际应该从Anvil获取
        for i in range(len(self.accounts)):
            # Anvil默认私钥模式
            private_key = f"0x{'ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80' if i == 0 else f'{i:064x}'}"
            self.private_keys.append(private_key)
    
    async def send_transaction_async(self, from_idx: int, to_idx: int, amount_eth: float) -> TransactionResult:
        """异步发送交易"""
        try:
            from_address = self.accounts[from_idx]
            to_address = self.accounts[to_idx]
            private_key = self.private_keys[from_idx]
            
            # 获取nonce
            nonce = self.w3.eth.get_transaction_count(from_address)
            
            # 构建交易
            transaction = {
                'to': to_address,
                'value': self.w3.to_wei(amount_eth, 'ether'),
                'gas': 21000,
                'gasPrice': self.w3.to_wei('1', 'gwei'),
                'nonce': nonce,
                'chainId': self.anvil.chain_id
            }
            
            # 签名交易
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
            
            # 发送交易
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # 等待交易确认
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            result = TransactionResult(
                tx_hash=tx_hash.hex(),
                from_address=from_address,
                to_address=to_address,
                amount=amount_eth,
                gas_used=receipt.gasUsed,
                status=receipt.status == 1,
                timestamp=time.time(),
                block_number=receipt.blockNumber
            )
            
            # 更新统计
            self.stats['total_transactions'] += 1
            if result.status:
                self.stats['successful_transactions'] += 1
            else:
                self.stats['failed_transactions'] += 1
            self.stats['total_gas_used'] += result.gas_used
            
            # 调用回调
            if self.on_transaction_complete:
                self.on_transaction_complete(result)
                
            return result
            
        except Exception as e:
            print(f"Transaction failed: {e}")
            self.stats['total_transactions'] += 1
            self.stats['failed_transactions'] += 1
            return None
    
    async def simulate_random_trading(self, 
                                    transactions_per_second: int = 10,
                                    duration_seconds: int = 60,
                                    min_amount: float = 0.01,
                                    max_amount: float = 1.0):
        """模拟随机交易"""
        self.running = True
        self.stats['start_time'] = time.time()
        
        interval = 1.0 / transactions_per_second
        end_time = time.time() + duration_seconds
        
        tasks = []
        
        while time.time() < end_time and self.running:
            # 随机选择发送方和接收方
            from_idx = random.randint(0, len(self.accounts) - 1)
            to_idx = random.randint(0, len(self.accounts) - 1)
            
            # 确保不是同一个账户
            while to_idx == from_idx:
                to_idx = random.randint(0, len(self.accounts) - 1)
            
            # 随机金额
            amount = random.uniform(min_amount, max_amount)
            
            # 创建异步任务
            task = asyncio.create_task(
                self.send_transaction_async(from_idx, to_idx, amount)
            )
            tasks.append(task)
            
            # 控制发送频率
            await asyncio.sleep(interval)
            
            # 清理已完成的任务
            tasks = [t for t in tasks if not t.done()]
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.running = False
    
    def simulate_high_frequency_trading(self, 
                                      batch_size: int = 100,
                                      batches: int = 10,
                                      delay_between_batches: float = 1.0):
        """高频交易模拟"""
        async def run_batch():
            tasks = []
            for _ in range(batch_size):
                from_idx = random.randint(0, len(self.accounts) - 1)
                to_idx = random.randint(0, len(self.accounts) - 1)
                while to_idx == from_idx:
                    to_idx = random.randint(0, len(self.accounts) - 1)
                
                amount = random.uniform(0.001, 0.1)
                task = self.send_transaction_async(from_idx, to_idx, amount)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        
        async def run_all_batches():
            for i in range(batches):
                print(f"Processing batch {i+1}/{batches}")
                await run_batch()
                if i < batches - 1:
                    await asyncio.sleep(delay_between_batches)
        
        asyncio.run(run_all_batches())
    
    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        elapsed_time = time.time() - self.stats['start_time'] if self.stats['start_time'] > 0 else 1
        
        return {
            'total_transactions': self.stats['total_transactions'],
            'successful_transactions': self.stats['successful_transactions'],
            'failed_transactions': self.stats['failed_transactions'],
            'success_rate': (self.stats['successful_transactions'] / max(self.stats['total_transactions'], 1)) * 100,
            'transactions_per_second': self.stats['total_transactions'] / elapsed_time,
            'total_gas_used': self.stats['total_gas_used'],
            'average_gas_per_tx': self.stats['total_gas_used'] / max(self.stats['total_transactions'], 1),
            'elapsed_time': elapsed_time
        }
    
    def stop(self):
        """停止模拟"""
        self.running = False