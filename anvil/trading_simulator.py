# trading_simulator.py (修复版)
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
        
        # 账户余额缓存
        self.balance_cache = {}
        self.last_balance_update = {}
        
        # 统计信息
        self.stats = {
            'total_transactions': 0,
            'successful_transactions': 0,
            'failed_transactions': 0,
            'insufficient_funds': 0,
            'total_gas_used': 0,
            'start_time': 0
        }
        
        self.on_transaction_complete: Optional[Callable] = None
        self.running = False
        
    def initialize(self):
        """初始化账户和私钥"""
        # 获取Anvil预生成的账户
        accounts = self.anvil.get_accounts()
        self.accounts = accounts[:50]  # 使用前50个账户
        
        # Anvil的默认私钥（基于固定助记词生成）
        # 这些是Anvil默认生成的前10个私钥
        default_private_keys = [
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
            "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
            "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
            "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
            "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
            "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
            "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
            "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
            "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
            "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6"
        ]
        
        # 为更多账户生成私钥（简化方式）
        self.private_keys = default_private_keys.copy()
        for i in range(len(default_private_keys), len(self.accounts)):
            # 生成额外的私钥（这里使用简化方法，实际应该从Anvil获取）
            private_key = f"0x{'%064x' % (int(default_private_keys[0], 16) + i)}"
            self.private_keys.append(private_key)
        
        # 初始化余额缓存
        self.update_balance_cache()
        
        print(f"初始化完成: {len(self.accounts)} 个账户")
        print(f"第一个账户余额: {self.w3.from_wei(self.get_balance(0), 'ether')} ETH")
    
    def get_balance(self, account_idx: int) -> int:
        """获取账户余额（wei）"""
        address = self.accounts[account_idx]
        current_time = time.time()
        
        # 如果缓存过期（超过5秒），更新余额
        if (address not in self.last_balance_update or 
            current_time - self.last_balance_update[address] > 5):
            try:
                balance = self.w3.eth.get_balance(address)
                self.balance_cache[address] = balance
                self.last_balance_update[address] = current_time
            except:
                # 如果获取失败，使用缓存值
                pass
        
        return self.balance_cache.get(address, 0)
    
    def update_balance_cache(self):
        """更新所有账户的余额缓存"""
        for i, address in enumerate(self.accounts):
            try:
                balance = self.w3.eth.get_balance(address)
                self.balance_cache[address] = balance
                self.last_balance_update[address] = time.time()
            except Exception as e:
                print(f"Failed to get balance for account {i}: {e}")
    
    def can_afford_transaction(self, account_idx: int, amount_wei: int) -> bool:
        """检查账户是否能承担交易费用"""
        balance = self.get_balance(account_idx)
        gas_cost = 21000 * self.w3.to_wei('2', 'gwei')  # 预估gas费用
        total_cost = amount_wei + gas_cost
        
        return balance >= total_cost
    
    def get_safe_amount(self, account_idx: int, max_amount_eth: float) -> float:
        """获取安全的交易金额"""
        balance = self.get_balance(account_idx)
        balance_eth = self.w3.from_wei(balance, 'ether')
        
        # 保留一些ETH用于gas费
        gas_reserve_eth = 0.01  # 保留0.01 ETH用于gas
        available_eth = max(0, balance_eth - gas_reserve_eth)
        
        # 返回可用余额和最大金额中的较小值
        return min(available_eth, max_amount_eth)
    
    async def send_transaction_async(self, from_idx: int, to_idx: int, amount_eth: float) -> TransactionResult:
        """异步发送交易"""
        try:
            from_address = self.accounts[from_idx]
            to_address = self.accounts[to_idx]
            private_key = self.private_keys[from_idx]
            
            # 检查并调整交易金额
            safe_amount = self.get_safe_amount(from_idx, amount_eth)
            if safe_amount <= 0:
                self.stats['insufficient_funds'] += 1
                raise Exception(f"Insufficient funds: available {safe_amount} ETH")
            
            amount_wei = self.w3.to_wei(safe_amount, 'ether')
            
            # 获取当前gas价格
            try:
                gas_price = self.w3.eth.gas_price
            except:
                gas_price = self.w3.to_wei('2', 'gwei')  # 默认2 gwei
            
            # 获取nonce
            nonce = self.w3.eth.get_transaction_count(from_address)
            
            # 构建交易
            transaction = {
                'to': to_address,
                'value': amount_wei,
                'gas': 21000,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': self.anvil.chain_id
            }
            
            # 最终检查余额
            balance = self.get_balance(from_idx)
            total_cost = amount_wei + (21000 * gas_price)
            
            if balance < total_cost:
                self.stats['insufficient_funds'] += 1
                raise Exception(f"Insufficient funds: need {self.w3.from_wei(total_cost, 'ether')} ETH, have {self.w3.from_wei(balance, 'ether')} ETH")
            
            # 签名交易
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
            
            # 发送交易
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # 等待交易确认
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            # 更新发送方余额缓存
            self.balance_cache[from_address] = balance - total_cost
            self.last_balance_update[from_address] = time.time()
            
            result = TransactionResult(
                tx_hash=tx_hash.hex(),
                from_address=from_address,
                to_address=to_address,
                amount=safe_amount,
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
                                    min_amount: float = 0.001,  # 降低最小金额
                                    max_amount: float = 0.1):   # 降低最大金额
        """模拟随机交易"""
        self.running = True
        self.stats['start_time'] = time.time()
        
        interval = 1.0 / transactions_per_second
        end_time = time.time() + duration_seconds
        
        tasks = []
        failed_attempts = 0
        max_failed_attempts = 100
        
        while time.time() < end_time and self.running and failed_attempts < max_failed_attempts:
            # 随机选择有足够余额的账户
            attempts = 0
            from_idx = None
            
            while attempts < 10:  # 最多尝试10次找到合适的账户
                candidate_idx = random.randint(0, len(self.accounts) - 1)
                safe_amount = self.get_safe_amount(candidate_idx, max_amount)
                
                if safe_amount >= min_amount:
                    from_idx = candidate_idx
                    break
                attempts += 1
            
            if from_idx is None:
                failed_attempts += 1
                print(f"Warning: Could not find account with sufficient balance (attempt {failed_attempts})")
                await asyncio.sleep(interval)
                continue
            
            # 重置失败计数
            failed_attempts = 0
            
            # 随机选择接收方
            to_idx = random.randint(0, len(self.accounts) - 1)
            while to_idx == from_idx:
                to_idx = random.randint(0, len(self.accounts) - 1)
            
            # 获取安全的交易金额
            safe_max_amount = self.get_safe_amount(from_idx, max_amount)
            amount = random.uniform(min_amount, min(safe_max_amount, max_amount))
            
            # 创建异步任务
            task = asyncio.create_task(
                self.send_transaction_async(from_idx, to_idx, amount)
            )
            tasks.append(task)
            
            # 控制发送频率
            await asyncio.sleep(interval)
            
            # 清理已完成的任务
            tasks = [t for t in tasks if not t.done()]
            
            # 定期更新余额缓存
            if len(tasks) % 50 == 0:
                self.update_balance_cache()
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.running = False
    
    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        elapsed_time = time.time() - self.stats['start_time'] if self.stats['start_time'] > 0 else 1
        
        return {
            'total_transactions': self.stats['total_transactions'],
            'successful_transactions': self.stats['successful_transactions'],
            'failed_transactions': self.stats['failed_transactions'],
            'insufficient_funds_errors': self.stats['insufficient_funds'],
            'success_rate': (self.stats['successful_transactions'] / max(self.stats['total_transactions'], 1)) * 100,
            'transactions_per_second': self.stats['total_transactions'] / elapsed_time,
            'total_gas_used': self.stats['total_gas_used'],
            'average_gas_per_tx': self.stats['total_gas_used'] / max(self.stats['total_transactions'], 1),
            'elapsed_time': elapsed_time
        }
    
    def stop(self):
        """停止模拟"""
        self.running = False