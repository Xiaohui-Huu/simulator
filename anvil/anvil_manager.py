# anvil_manager.py
import subprocess
import time
import requests
import json
from typing import Optional, List, Dict
from eth_utils import to_checksum_address

class AnvilManager:
    def __init__(self, port: int = 8545, chain_id: int = 31337, accounts: int = 50):
        self.port = port
        self.chain_id = chain_id
        self.accounts = accounts
        self.process: Optional[subprocess.Popen] = None
        self.rpc_url = f"http://localhost:{port}"
        
    def start(self, block_time: int = 2) -> bool:
        """启动Anvil节点"""
        try:
            cmd = [
                "anvil",
                "--port", str(self.port),
                "--chain-id", str(self.chain_id),
                "--accounts", str(self.accounts),
                "--balance", "100000",        # 增加到100,000 ETH
                "--block-time", str(block_time),
                "--gas-limit", "30000000",
                "--gas-price", "1000000000",  # 1 gwei
                "--base-fee", "1000000000"    # 设置基础费用
            ]
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待节点启动
            for _ in range(30):
                if self.is_running():
                    print(f"Anvil started on port {self.port}")
                    return True
                time.sleep(1)
                
            return False
            
        except Exception as e:
            print(f"Failed to start Anvil: {e}")
            return False
    
    def stop(self):
        """停止Anvil节点"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            print("Anvil stopped")
    
    def is_running(self) -> bool:
        """检查节点是否运行"""
        try:
            response = requests.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 1
                },
                timeout=2
            )
            return response.status_code == 200
        except:
            return False
    
    def get_accounts(self) -> List[str]:
        """获取所有账户地址"""
        try:
            response = requests.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_accounts",
                    "params": [],
                    "id": 1
                }
            )
            return response.json()["result"]
        except:
            return []