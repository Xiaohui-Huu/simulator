import subprocess
import json
import time
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from web3 import Web3
import requests

@dataclass
class SimulationConfig:
    """模拟配置类"""
    rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 31337
    gas_limit: int = 30000000
    gas_price: int = 20000000000  # 20 gwei
    block_time: int = 12  # seconds

@dataclass
class Account:
    """账户信息类"""
    address: str
    private_key: str
    balance: int = 0

class FoundryManager:
    """Foundry管理器"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.process = None
        self.web3 = None
        
    def start_anvil(self, accounts: int = 10, balance: int = 10000) -> bool:
        """启动Anvil本地节点"""
        try:
            cmd = [
                "anvil",
                "--host", "0.0.0.0",
                "--port", "8545",
                "--accounts", str(accounts),
                "--balance", str(balance),
                "--gas-limit", str(self.config.gas_limit),
                "--gas-price", str(self.config.gas_price),
                "--block-time", str(self.config.block_time)
            ]
            
            print("启动Anvil节点...")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待节点启动
            time.sleep(3)
            
            # 初始化Web3连接
            self.web3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            
            if self.web3.is_connected():
                print(f"✅ Anvil节点已启动，RPC地址: {self.config.rpc_url}")
                return True
            else:
                print("❌ 无法连接到Anvil节点")
                return False
                
        except Exception as e:
            print(f"❌ 启动Anvil失败: {e}")
            return False
    
    def stop_anvil(self):
        """停止Anvil节点"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            print("🛑 Anvil节点已停止")
    
    def get_accounts(self) -> List[Account]:
        """获取预设账户列表"""
        if not self.web3:
            return []
        
        accounts = []
        try:
            # 获取账户地址
            addresses = self.web3.eth.accounts
            
            # 预设私钥（Anvil默认私钥）
            default_private_keys = [
                "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
                "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c6a2440a2b8c6b8b8b8b8",
                "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
                "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
                "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
                "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
                "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
                "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
                "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
                "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6"
            ]
            
            for i, address in enumerate(addresses[:len(default_private_keys)]):
                balance = self.web3.eth.get_balance(address)
                accounts.append(Account(
                    address=address,
                    private_key=default_private_keys[i],
                    balance=balance
                ))
            
            return accounts
            
        except Exception as e:
            print(f"❌ 获取账户失败: {e}")
            return []

class TransactionSimulator:
    """交易模拟器"""
    
    def __init__(self, foundry_manager: FoundryManager):
        self.foundry = foundry_manager
        self.web3 = foundry_manager.web3
        
    def send_eth_transaction(self, from_account: Account, to_address: str, 
                           amount_eth: float) -> Optional[str]:
        """发送ETH转账交易"""
        try:
            # 构建交易
            transaction = {
                'to': to_address,
                'value': self.web3.to_wei(amount_eth, 'ether'),
                'gas': 21000,
                'gasPrice': self.foundry.config.gas_price,
                'nonce': self.web3.eth.get_transaction_count(from_account.address),
                'chainId': self.foundry.config.chain_id
            }
            
            # 签名交易
            signed_txn = self.web3.eth.account.sign_transaction(
                transaction, from_account.private_key
            )
            
            # 发送交易
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            print(f"📤 发送交易: {tx_hash.hex()}")
            print(f"   从: {from_account.address}")
            print(f"   到: {to_address}")
            print(f"   金额: {amount_eth} ETH")
            
            return tx_hash.hex()
            
        except Exception as e:
            print(f"❌ 发送交易失败: {e}")
            return None
    
    def deploy_contract(self, from_account: Account, bytecode: str, 
                       constructor_args: List = None) -> Optional[str]:
        """部署智能合约"""
        try:
            # 构建部署交易
            transaction = {
                'data': bytecode,
                'gas': 3000000,
                'gasPrice': self.foundry.config.gas_price,
                'nonce': self.web3.eth.get_transaction_count(from_account.address),
                'chainId': self.foundry.config.chain_id
            }
            
            # 签名交易
            signed_txn = self.web3.eth.account.sign_transaction(
                transaction, from_account.private_key
            )
            
            # 发送交易
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # 等待交易确认
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            
            print(f"📋 合约部署成功:")
            print(f"   交易哈希: {tx_hash.hex()}")
            print(f"   合约地址: {receipt.contractAddress}")
            
            return receipt.contractAddress
            
        except Exception as e:
            print(f"❌ 合约部署失败: {e}")
            return None
    
    def call_contract_function(self, from_account: Account, contract_address: str,
                             function_data: str) -> Optional[str]:
        """调用合约函数"""
        try:
            # 构建交易
            transaction = {
                'to': contract_address,
                'data': function_data,
                'gas': 200000,
                'gasPrice': self.foundry.config.gas_price,
                'nonce': self.web3.eth.get_transaction_count(from_account.address),
                'chainId': self.foundry.config.chain_id
            }
            
            # 签名交易
            signed_txn = self.web3.eth.account.sign_transaction(
                transaction, from_account.private_key
            )
            
            # 发送交易
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            print(f"🔧 调用合约函数: {tx_hash.hex()}")
            print(f"   合约地址: {contract_address}")
            
            return tx_hash.hex()
            
        except Exception as e:
            print(f"❌ 调用合约函数失败: {e}")
            return None
    
    def batch_transactions(self, transactions: List[Dict]) -> List[str]:
        """批量发送交易"""
        tx_hashes = []
        
        for i, tx_data in enumerate(transactions):
            print(f"\n📦 执行批量交易 {i+1}/{len(transactions)}")
            
            if tx_data['type'] == 'transfer':
                tx_hash = self.send_eth_transaction(
                    tx_data['from_account'],
                    tx_data['to_address'],
                    tx_data['amount']
                )
            elif tx_data['type'] == 'contract_call':
                tx_hash = self.call_contract_function(
                    tx_data['from_account'],
                    tx_data['contract_address'],
                    tx_data['function_data']
                )
            
            if tx_hash:
                tx_hashes.append(tx_hash)
            
            # 添加延迟避免nonce冲突
            time.sleep(1)
        
        return tx_hashes

class SimulationScenarios:
    """模拟场景类"""
    
    def __init__(self, simulator: TransactionSimulator, accounts: List[Account]):
        self.simulator = simulator
        self.accounts = accounts
    
    def scenario_simple_transfers(self):
        """场景1: 简单转账"""
        print("\n🎬 执行场景: 简单转账")
        
        if len(self.accounts) < 3:
            print("❌ 需要至少3个账户")
            return
        
        # 账户A向账户B转账1 ETH
        self.simulator.send_eth_transaction(
            self.accounts[0], self.accounts[1].address, 1.0
        )
        
        # 账户B向账户C转账0.5 ETH
        time.sleep(2)
        self.simulator.send_eth_transaction(
            self.accounts[1], self.accounts[2].address, 0.5
        )
    
    def scenario_batch_transfers(self):
        """场景2: 批量转账"""
        print("\n🎬 执行场景: 批量转账")
        
        if len(self.accounts) < 5:
            print("❌ 需要至少5个账户")
            return
        
        # 准备批量交易
        transactions = []
        for i in range(1, 4):
            transactions.append({
                'type': 'transfer',
                'from_account': self.accounts[0],
                'to_address': self.accounts[i].address,
                'amount': 0.1 * i
            })
        
        self.simulator.batch_transactions(transactions)
    
    def scenario_contract_deployment(self):
        """场景3: 合约部署和调用"""
        print("\n🎬 执行场景: 合约部署")
        
        # 简单的存储合约字节码 (存储一个数字)
        simple_storage_bytecode = "0x608060405234801561001057600080fd5b50610150806100206000396000f3fe608060405234801561001057600080fd5b50600436106100365760003560e01c80632e64cec11461003b5780636057361d14610059575b600080fd5b610043610075565b60405161005091906100a1565b60405180910390f35b610073600480360381019061006e91906100ed565b61007e565b005b60008054905090565b8060008190555050565b6000819050919050565b61009b81610088565b82525050565b60006020820190506100b66000830184610092565b92915050565b600080fd5b6100ca81610088565b81146100d557600080fd5b50565b6000813590506100e7816100c1565b92915050565b600060208284031215610103576101026100bc565b5b6000610111848285016100d8565b9150509291505056fea2646970667358221220a6a0e11af79f176f9c421b7b12f441356b25f6489b83a22a3a55c65d98f4a58064736f6c63430008120033"
        
        # 部署合约
        contract_address = self.simulator.deploy_contract(
            self.accounts[0], simple_storage_bytecode
        )
        
        if contract_address:
            # 调用合约函数 (设置值为42)
            function_data = "0x6057361d000000000000000000000000000000000000000000000000000000000000002a"
            self.simulator.call_contract_function(
                self.accounts[0], contract_address, function_data
            )

class EthereumSimulator:
    """以太坊模拟器主类"""
    
    def __init__(self):
        self.config = SimulationConfig()
        self.foundry = FoundryManager(self.config)
        self.simulator = None
        self.scenarios = None
        self.accounts = []
    
    def start(self):
        """启动模拟器"""
        print("🚀 启动以太坊交易模拟器")
        
        # 启动Anvil节点
        if not self.foundry.start_anvil():
            return False
        
        # 获取账户
        self.accounts = self.foundry.get_accounts()
        if not self.accounts:
            print("❌ 无法获取账户")
            return False
        
        print(f"📋 获取到 {len(self.accounts)} 个账户:")
        for i, account in enumerate(self.accounts[:3]):  # 只显示前3个
            balance_eth = self.foundry.web3.from_wei(account.balance, 'ether')
            print(f"   账户{i}: {account.address} (余额: {balance_eth} ETH)")
        
        # 初始化模拟器和场景
        self.simulator = TransactionSimulator(self.foundry)
        self.scenarios = SimulationScenarios(self.simulator, self.accounts)
        
        return True
    
    def run_all_scenarios(self):
        """运行所有模拟场景"""
        if not self.scenarios:
            print("❌ 模拟器未初始化")
            return
        
        print("\n🎭 开始执行所有模拟场景")
        
        # 执行各种场景
        self.scenarios.scenario_simple_transfers()
        time.sleep(3)
        
        self.scenarios.scenario_batch_transfers()
        time.sleep(3)
        
        self.scenarios.scenario_contract_deployment()
        
        print("\n✅ 所有模拟场景执行完成")
    
    def interactive_mode(self):
        """交互模式"""
        while True:
            print("\n" + "="*50)
            print("🎮 以太坊交易模拟器 - 交互模式")
            print("="*50)
            print("1. 查看账户信息")
            print("2. 发送ETH转账")
            print("3. 批量转账")
            print("4. 部署合约")
            print("5. 运行预设场景")
            print("6. 查看区块信息")
            print("0. 退出")
            
            choice = input("\n请选择操作 (0-6): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                self._show_account_info()
            elif choice == '2':
                self._interactive_transfer()
            elif choice == '3':
                self._interactive_batch_transfer()
            elif choice == '4':
                self._interactive_deploy_contract()
            elif choice == '5':
                self.run_all_scenarios()
            elif choice == '6':
                self._show_block_info()
            else:
                print("❌ 无效选择")
    
    def _show_account_info(self):
        """显示账户信息"""
        print("\n📋 账户信息:")
        for i, account in enumerate(self.accounts):
            balance = self.foundry.web3.eth.get_balance(account.address)
            balance_eth = self.foundry.web3.from_wei(balance, 'ether')
            print(f"账户{i}: {account.address}")
            print(f"  余额: {balance_eth} ETH")
            print(f"  私钥: {account.private_key}")
            print()
    
    def _interactive_transfer(self):
        """交互式转账"""
        try:
            print("\n💸 发送ETH转账")
            from_idx = int(input(f"选择发送方账户 (0-{len(self.accounts)-1}): "))
            to_idx = int(input(f"选择接收方账户 (0-{len(self.accounts)-1}): "))
            amount = float(input("输入转账金额 (ETH): "))
            
            if 0 <= from_idx < len(self.accounts) and 0 <= to_idx < len(self.accounts):
                self.simulator.send_eth_transaction(
                    self.accounts[from_idx],
                    self.accounts[to_idx].address,
                    amount
                )
            else:
                print("❌ 账户索引无效")
        except (ValueError, IndexError):
            print("❌ 输入无效")
    
    def _interactive_batch_transfer(self):
        """交互式批量转账"""
        try:
            print("\n📦 批量转账")
            from_idx = int(input(f"选择发送方账户 (0-{len(self.accounts)-1}): "))
            count = int(input("输入转账笔数: "))
            
            if not (0 <= from_idx < len(self.accounts)):
                print("❌ 发送方账户索引无效")
                return
            
            transactions = []
            for i in range(count):
                print(f"\n第 {i+1} 笔转账:")
                to_idx = int(input(f"  接收方账户 (0-{len(self.accounts)-1}): "))
                amount = float(input("  转账金额 (ETH): "))
                
                if 0 <= to_idx < len(self.accounts):
                    transactions.append({
                        'type': 'transfer',
                        'from_account': self.accounts[from_idx],
                        'to_address': self.accounts[to_idx].address,
                        'amount': amount
                    })
            
            if transactions:
                self.simulator.batch_transactions(transactions)
                
        except (ValueError, IndexError):
            print("❌ 输入无效")
    
    def _interactive_deploy_contract(self):
        """交互式部署合约"""
        print("\n📋 部署智能合约")
        print("使用预设的简单存储合约")
        
        try:
            from_idx = int(input(f"选择部署账户 (0-{len(self.accounts)-1}): "))
            
            if 0 <= from_idx < len(self.accounts):
                simple_storage_bytecode = "0x608060405234801561001057600080fd5b50610150806100206000396000f3fe608060405234801561001057600080fd5b50600436106100365760003560e01c80632e64cec11461003b5780636057361d14610059575b600080fd5b610043610075565b60405161005091906100a1565b60405180910390f35b610073600480360381019061006e91906100ed565b61007e565b005b60008054905090565b8060008190555050565b6000819050919050565b61009b81610088565b82525050565b60006020820190506100b66000830184610092565b92915050565b600080fd5b6100ca81610088565b81146100d557600080fd5b50565b6000813590506100e7816100c1565b92915050565b600060208284031215610103576101026100bc565b5b6000610111848285016100d8565b9150509291505056fea2646970667358221220a6a0e11af79f176f9c421b7b12f441356b25f6489b83a22a3a55c65d98f4a58064736f6c63430008120033"
                
                self.simulator.deploy_contract(
                    self.accounts[from_idx], simple_storage_bytecode
                )
            else:
                print("❌ 账户索引无效")
        except (ValueError, IndexError):
            print("❌ 输入无效")
    
    def _show_block_info(self):
        """显示区块信息"""
        try:
            latest_block = self.foundry.web3.eth.get_block('latest')
            print(f"\n🧱 最新区块信息:")
            print(f"区块号: {latest_block.number}")
            print(f"区块哈希: {latest_block.hash.hex()}")
            print(f"时间戳: {latest_block.timestamp}")
            print(f"交易数量: {len(latest_block.transactions)}")
            print(f"Gas使用: {latest_block.gasUsed}")
            print(f"Gas限制: {latest_block.gasLimit}")
        except Exception as e:
            print(f"❌ 获取区块信息失败: {e}")
    
    def stop(self):
        """停止模拟器"""
        print("\n🛑 停止模拟器")
        self.foundry.stop_anvil()

def main():
    """主函数"""
    simulator = EthereumSimulator()
    
    try:
        # 启动模拟器
        if not simulator.start():
            print("❌ 模拟器启动失败")
            return
        
        print("\n✅ 模拟器启动成功!")
        
        # 询问运行模式
        print("\n选择运行模式:")
        print("1. 自动运行所有场景")
        print("2. 交互模式")
        
        mode = input("请选择 (1-2): ").strip()
        
        if mode == '1':
            simulator.run_all_scenarios()
        elif mode == '2':
            simulator.interactive_mode()
        else:
            print("运行默认场景...")
            simulator.run_all_scenarios()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n❌ 运行错误: {e}")
    finally:
        simulator.stop()

if __name__ == "__main__":
    main()