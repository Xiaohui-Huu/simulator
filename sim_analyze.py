from web3 import Web3
from typing import Dict, List, Any, Optional, Tuple
import json
from dataclasses import dataclass

@dataclass
class Transfer:
    """转账信息数据类"""
    sender: str
    receiver: str
    amount: int
    token_address: Optional[str]  # None表示ETH转账
    token_symbol: Optional[str] = None
    token_decimals: Optional[int] = None
    transfer_type: str = "UNKNOWN"  # ETH, ERC20, ERC721, ERC1155等

class TransferAnalyzer:
    def __init__(self, web3_instance: Web3):
        self.w3 = web3_instance
        
        # ERC20 Transfer事件签名
        self.ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        # ERC721 Transfer事件签名 (与ERC20相同)
        self.ERC721_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        # ERC1155 TransferSingle事件签名
        self.ERC1155_TRANSFER_SINGLE_TOPIC = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
        
        # ERC1155 TransferBatch事件签名
        self.ERC1155_TRANSFER_BATCH_TOPIC = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
        
        # WETH Deposit/Withdrawal事件签名
        self.WETH_DEPOSIT_TOPIC = "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c"
        self.WETH_WITHDRAWAL_TOPIC = "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"
        
        # 常见的ERC20 ABI用于获取代币信息
        self.ERC20_ABI = [
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals", 
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]
        
        # 缓存代币信息
        self.token_info_cache = {}
    
    def analyze_all_transfers(self, transaction_result: Dict[str, Any]) -> List[Transfer]:
        """
        分析交易结果中的所有转账操作
        
        Args:
            transaction_result: 从EthereumTransactionSimulator获得的交易结果
            
        Returns:
            所有转账操作的列表
        """
        transfers = []
        
        # 1. 分析ETH转账 (从交易本身和internal transactions)
        eth_transfers = self._analyze_eth_transfers(transaction_result)
        transfers.extend(eth_transfers)
        
        # 2. 分析ERC20/ERC721/ERC1155转账 (从logs)
        token_transfers = self._analyze_token_transfers(transaction_result.get('logs', []))
        transfers.extend(token_transfers)
        
        # 3. 分析特殊合约转账 (如WETH)
        special_transfers = self._analyze_special_transfers(transaction_result.get('logs', []))
        transfers.extend(special_transfers)
        
        return transfers
    
    def _analyze_eth_transfers(self, transaction_result: Dict[str, Any]) -> List[Transfer]:
        """分析ETH转账"""
        transfers = []
        
        # 主交易的ETH转账
        tx_details = transaction_result.get('transaction_details', {})
        if tx_details.get('value', 0) > 0:
            transfers.append(Transfer(
                sender=tx_details['from'],
                receiver=tx_details['to'],
                amount=int(tx_details['value']),
                token_address=None,
                token_symbol="ETH",
                token_decimals=18,
                transfer_type="ETH"
            ))
        
        # Internal transactions中的ETH转账
        for internal_tx in transaction_result.get('internal_transactions', []):
            value = internal_tx.get('value', '0x0')
            if isinstance(value, str) and value.startswith('0x'):
                value = int(value, 16)
            elif isinstance(value, str):
                value = int(value)
            
            if value > 0 and internal_tx.get('from') and internal_tx.get('to'):
                transfers.append(Transfer(
                    sender=internal_tx['from'],
                    receiver=internal_tx['to'],
                    amount=value,
                    token_address=None,
                    token_symbol="ETH",
                    token_decimals=18,
                    transfer_type="ETH_INTERNAL"
                ))
        
        return transfers
    
    def _analyze_token_transfers(self, logs: List[Dict[str, Any]]) -> List[Transfer]:
        """分析代币转账事件"""
        transfers = []
        
        for log in logs:
            topics = log.get('topics', [])
            if not topics:
                continue
                
            topic0 = topics[0] if isinstance(topics[0], str) else topics[0]
            
            # ERC20/ERC721 Transfer事件
            if topic0 == self.ERC20_TRANSFER_TOPIC:
                transfer = self._parse_erc20_transfer(log)
                if transfer:
                    transfers.append(transfer)
            
            # ERC1155 TransferSingle事件
            elif topic0 == self.ERC1155_TRANSFER_SINGLE_TOPIC:
                transfer = self._parse_erc1155_single_transfer(log)
                if transfer:
                    transfers.append(transfer)
            
            # ERC1155 TransferBatch事件
            elif topic0 == self.ERC1155_TRANSFER_BATCH_TOPIC:
                batch_transfers = self._parse_erc1155_batch_transfer(log)
                transfers.extend(batch_transfers)
        
        return transfers
    
    def _parse_erc20_transfer(self, log: Dict[str, Any]) -> Optional[Transfer]:
        """解析ERC20/ERC721 Transfer事件"""
        try:
            topics = log['topics']
            data = log['data']
            token_address = log['address']
            
            # Transfer(address indexed from, address indexed to, uint256 value)
            if len(topics) >= 3:
                # 去除0x前缀并补齐到64位
                from_addr = "0x" + topics[1][-40:]  # 取后40个字符
                to_addr = "0x" + topics[2][-40:]    # 取后40个字符
                
                # 解析amount
                if data.startswith('0x'):
                    data = data[2:]
                
                # 确保data长度是64的倍数
                if len(data) % 64 != 0:
                    data = data.zfill((len(data) // 64 + 1) * 64)
                
                amount = int(data[:64], 16) if data else 0
                
                # 获取代币信息
                token_info = self._get_token_info(token_address)
                
                # 判断是ERC20还是ERC721
                transfer_type = "ERC721" if amount == 1 and self._is_erc721(token_address) else "ERC20"
                
                return Transfer(
                    sender=from_addr,
                    receiver=to_addr,
                    amount=amount,
                    token_address=token_address,
                    token_symbol=token_info.get('symbol'),
                    token_decimals=token_info.get('decimals'),
                    transfer_type=transfer_type
                )
        except Exception as e:
            print(f"解析ERC20 Transfer事件失败: {e}")
            print(f"Log: {log}")
        
        return None
    
    def _parse_erc1155_single_transfer(self, log: Dict[str, Any]) -> Optional[Transfer]:
        """解析ERC1155 TransferSingle事件"""
        try:
            topics = log['topics']
            data = log['data']
            token_address = log['address']
            
            # TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value)
            if len(topics) >= 4:
                from_addr = "0x" + topics[2][-40:]
                to_addr = "0x" + topics[3][-40:]
                
                if data.startswith('0x'):
                    data = data[2:]
                
                # ERC1155的data包含id和value
                if len(data) >= 128:
                    token_id = int(data[:64], 16)
                    amount = int(data[64:128], 16)
                    
                    token_info = self._get_token_info(token_address)
                    
                    return Transfer(
                        sender=from_addr,
                        receiver=to_addr,
                        amount=amount,
                        token_address=token_address,
                        token_symbol=f"{token_info.get('symbol', 'ERC1155')}#{token_id}",
                        token_decimals=0,  # ERC1155通常不使用decimals
                        transfer_type="ERC1155"
                    )
        except Exception as e:
            print(f"解析ERC1155 TransferSingle事件失败: {e}")
        
        return None
    
    def _parse_erc1155_batch_transfer(self, log: Dict[str, Any]) -> List[Transfer]:
        """解析ERC1155 TransferBatch事件"""
        transfers = []
        try:
            topics = log['topics']
            data = log['data']
            token_address = log['address']
            
            # TransferBatch(address indexed operator, address indexed from, address indexed to, uint256[] ids, uint256[] values)
            if len(topics) >= 4:
                from_addr = "0x" + topics[2][-40:]
                to_addr = "0x" + topics[3][-40:]
                
                # 解析批量转账数据比较复杂，这里简化处理
                # 实际应用中需要根据ABI正确解码数组数据
                token_info = self._get_token_info(token_address)
                
                # 简化：假设是单个批量转账
                transfers.append(Transfer(
                    sender=from_addr,
                    receiver=to_addr,
                    amount=1,  # 批量转账的具体数量需要更复杂的解析
                    token_address=token_address,
                    token_symbol=f"{token_info.get('symbol', 'ERC1155')}_BATCH",
                    token_decimals=0,
                    transfer_type="ERC1155_BATCH"
                ))
        except Exception as e:
            print(f"解析ERC1155 TransferBatch事件失败: {e}")
        
        return transfers
    
    def _analyze_special_transfers(self, logs: List[Dict[str, Any]]) -> List[Transfer]:
        """分析特殊合约的转账 (如WETH Deposit/Withdrawal)"""
        transfers = []
        
        for log in logs:
            topics = log.get('topics', [])
            if not topics:
                continue
                
            topic0 = topics[0] if isinstance(topics[0], str) else topics[0]
            
            # WETH Deposit事件
            if topic0 == self.WETH_DEPOSIT_TOPIC:
                transfer = self._parse_weth_deposit(log)
                if transfer:
                    transfers.append(transfer)
            
            # WETH Withdrawal事件  
            elif topic0 == self.WETH_WITHDRAWAL_TOPIC:
                transfer = self._parse_weth_withdrawal(log)
                if transfer:
                    transfers.append(transfer)
        
        return transfers
    
    def _parse_weth_deposit(self, log: Dict[str, Any]) -> Optional[Transfer]:
        """解析WETH Deposit事件"""
        try:
            topics = log['topics']
            data = log['data']
            weth_address = log['address']
            
            # Deposit(address indexed dst, uint wad)
            if len(topics) >= 2:
                dst_addr = "0x" + topics[1][-40:]
                
                if data.startswith('0x'):
                    data = data[2:]
                
                amount = int(data[:64], 16) if data else 0
                
                return Transfer(
                    sender="0x0000000000000000000000000000000000000000",  # ETH -> WETH
                    receiver=dst_addr,
                    amount=amount,
                    token_address=weth_address,
                    token_symbol="WETH",
                    token_decimals=18,
                    transfer_type="WETH_DEPOSIT"
                )
        except Exception as e:
            print(f"解析WETH Deposit事件失败: {e}")
        
        return None
    
    def _parse_weth_withdrawal(self, log: Dict[str, Any]) -> Optional[Transfer]:
        """解析WETH Withdrawal事件"""
        try:
            topics = log['topics']
            data = log['data']
            weth_address = log['address']
            
            # Withdrawal(address indexed src, uint wad)
            if len(topics) >= 2:
                src_addr = "0x" + topics[1][-40:]
                
                if data.startswith('0x'):
                    data = data[2:]
                
                amount = int(data[:64], 16) if data else 0
                
                return Transfer(
                    sender=src_addr,
                    receiver="0x0000000000000000000000000000000000000000",  # WETH -> ETH
                    amount=amount,
                    token_address=weth_address,
                    token_symbol="WETH",
                    token_decimals=18,
                    transfer_type="WETH_WITHDRAWAL"
                )
        except Exception as e:
            print(f"解析WETH Withdrawal事件失败: {e}")
        
        return None
    
    def _get_token_info(self, token_address: str) -> Dict[str, Any]:
        """获取代币信息 (symbol, decimals, name)"""
        if token_address in self.token_info_cache:
            return self.token_info_cache[token_address]
        
        info = {'symbol': None, 'decimals': None, 'name': None}
        
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            # 尝试获取symbol
            try:
                info['symbol'] = contract.functions.symbol().call()
            except:
                pass
            
            # 尝试获取decimals
            try:
                info['decimals'] = contract.functions.decimals().call()
            except:
                pass
            
            # 尝试获取name
            try:
                info['name'] = contract.functions.name().call()
            except:
                pass
                
        except Exception as e:
            print(f"获取代币信息失败 {token_address}: {e}")
        
        self.token_info_cache[token_address] = info
        return info
    
    def _is_erc721(self, token_address: str) -> bool:
        """简单判断是否为ERC721代币"""
        # 这里可以实现更复杂的ERC721检测逻辑
        # 例如检查是否实现了ERC721接口
        return False  # 简化实现
    
    def format_transfers(self, transfers: List[Transfer]) -> str:
        """格式化转账信息为可读字符串"""
        if not transfers:
            return "未发现任何转账操作"
        
        result = f"发现 {len(transfers)} 个转账操作:\n"
        result += "=" * 80 + "\n"
        
        for i, transfer in enumerate(transfers, 1):
            result += f"{i}. {transfer.transfer_type} 转账:\n"
            result += f"   发送方: {transfer.sender}\n"
            result += f"   接收方: {transfer.receiver}\n"
            print(transfer.sender)
            print(transfer.receiver)
            
            if transfer.token_address:
                # 代币转账
                if transfer.token_decimals is not None:
                    formatted_amount = transfer.amount / (10 ** transfer.token_decimals)
                    result += f"   金额: {formatted_amount} {transfer.token_symbol or 'UNKNOWN'}\n"
                else:
                    result += f"   金额: {transfer.amount} {transfer.token_symbol or 'UNKNOWN'}\n"
                result += f"   代币地址: {transfer.token_address}\n"
            else:
                # ETH转账
                eth_amount = transfer.amount / (10 ** 18)
                result += f"   金额: {eth_amount} ETH\n"
            
            result += "-" * 40 + "\n"
        
        return result

# 扩展原有的EthereumTransactionSimulator类
class EnhancedTransactionSimulator:
    def __init__(self, anvil_url: str = "http://127.0.0.1:8545"):
        from test import EthereumTransactionSimulator  # 导入原有类
        
        self.simulator = EthereumTransactionSimulator(anvil_url)
        self.analyzer = TransferAnalyzer(self.simulator.w3)
    
    def simulate_and_analyze_transfers(
        self,
        from_address: str,
        to_address: str,
        data: str = "0x",
        value: int = 0,
        gas_limit: int = 21000000
    ) -> Dict[str, Any]:
        """
        模拟交易并分析所有转账操作
        """
        # 执行交易模拟
        tx_result = self.simulator.simulate_transaction(
            from_address, to_address, data, value, gas_limit
        )
        
        # 分析转账操作
        transfers = self.analyzer.analyze_all_transfers(tx_result)
        
        # 添加转账分析结果
        tx_result['transfers'] = [
            {
                'sender': t.sender,
                'receiver': t.receiver,
                'amount': t.amount,
                'token_address': t.token_address,
                'token_symbol': t.token_symbol,
                'token_decimals': t.token_decimals,
                'transfer_type': t.transfer_type
            }
            for t in transfers
        ]
        
        tx_result['transfer_summary'] = self.analyzer.format_transfers(transfers)
        
        return tx_result

def main():
    """示例使用"""
    # 创建增强的模拟器
    enhanced_simulator = EnhancedTransactionSimulator()
    
    # 示例：模拟一个复杂的DeFi交易
    from_address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
    to_address = "0x15B8847Df668656EE316Aa97Ba574b4AF2213CB6"
    data = "0xaad3ec96000000000000000000000000ca0f5168bce57c2ab9610fc92c5a4536ecec87780000000000000000000000000000000000000000000000000000000000000055"
    value = Web3.to_wei(0.1, 'ether')
    
    print("开始模拟交易并分析转账...")
    
    result = enhanced_simulator.simulate_and_analyze_transfers(
        from_address=from_address,
        to_address=to_address,
        data=data,
        value=value
    )
    
    # 打印转账分析结果
    print("\n" + "="*50)
    print("转账分析结果:")
    print("="*50)
    print(result['transfer_summary'])
    
    # 保存详细结果
    with open('transfer_analysis_result.json', 'a') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n详细结果已保存到 transfer_analysis_result.json")

if __name__ == "__main__":
    main()