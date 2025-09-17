from web3 import Web3
from eth_account import Account
import json
from typing import Dict, List, Any, Optional

class EthereumTransactionSimulator:
    def __init__(self, anvil_url: str = "http://127.0.0.1:8545"):
        """
        初始化以太坊交易模拟器
        
        Args:
            anvil_url: Anvil节点的RPC URL
        """
        self.w3 = Web3(Web3.HTTPProvider(anvil_url))
        
        # 验证连接
        if not self.w3.is_connected():
            raise Exception(f"无法连接到Anvil节点: {anvil_url}")
        
        print(f"已连接到Anvil节点，链ID: {self.w3.eth.chain_id}")
    
    def simulate_transaction(
        self, 
        from_address: str, 
        to_address: str, 
        data: str = "0x", 
        value: int = 0,
        gas_limit: int = 21000000
    ) -> Dict[str, Any]:
        """
        模拟交易并获取internal transactions和logs
        
        Args:
            from_address: 发送方地址
            to_address: 接收方地址  
            data: 交易数据 (hex格式)
            value: 发送的ETH数量 (wei)
            gas_limit: Gas限制
            
        Returns:
            包含交易结果、internal transactions和logs的字典
        """
        
        # 构建交易
        transaction = {
            'from': from_address,
            'to': to_address,
            'data': data,
            'value': value,
            'gas': gas_limit,
            'gasPrice': self.w3.eth.gas_price
        }
        
        try:
            # 1. 首先使用eth_call进行静态调用，获取返回值
            call_result = self.w3.eth.call(transaction)
            
            # 2. 使用debug_traceCall获取详细的执行跟踪
            trace_result = self.w3.manager.request_blocking(
                "debug_traceCall",
                [transaction, "latest", {"tracer": "callTracer"}]
            )
            
            # 3. 发送实际交易获取logs
            # 获取nonce
            nonce = self.w3.eth.get_transaction_count(from_address)
            transaction['nonce'] = nonce
            
            # 发送交易
            tx_hash = self.w3.eth.send_transaction(transaction)
            
            # 等待交易被挖掘
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # 获取交易详情
            tx_details = self.w3.eth.get_transaction(tx_hash)
            
            # 解析internal transactions
            internal_txs = self._parse_internal_transactions(trace_result)
            
            # 获取所有logs
            logs = self._parse_logs(tx_receipt.logs)
            
            return {
                'transaction_hash': tx_hash.hex(),
                'status': tx_receipt.status,
                'gas_used': tx_receipt.gasUsed,
                'call_result': call_result.hex() if call_result else None,
                'internal_transactions': internal_txs,
                'logs': logs,
                'transaction_details': {
                    'from': tx_details['from'],
                    'to': tx_details['to'],
                    'value': tx_details['value'],
                    'data': tx_details['input'].hex(),
                    'gas': tx_details['gas'],
                    'gasPrice': tx_details['gasPrice']
                }
            }
            
        except Exception as e:
            print(f"交易模拟失败: {str(e)}")
            
            # 如果实际交易失败，尝试只做静态调用和跟踪
            try:
                call_result = self.w3.eth.call(transaction)
                trace_result = self.w3.manager.request_blocking(
                    "debug_traceCall",
                    [transaction, "latest", {"tracer": "callTracer"}]
                )
                
                internal_txs = self._parse_internal_transactions(trace_result)
                
                return {
                    'transaction_hash': None,
                    'status': 'simulation_only',
                    'error': str(e),
                    'call_result': call_result.hex() if call_result else None,
                    'internal_transactions': internal_txs,
                    'logs': [],
                    'transaction_details': transaction
                }
            except Exception as e2:
                return {
                    'error': f"模拟失败: {str(e2)}",
                    'original_error': str(e)
                }
    
    def _parse_internal_transactions(self, trace_result: Dict) -> List[Dict[str, Any]]:
        """
        解析internal transactions从trace结果
        """
        internal_txs = []
        
        def extract_calls(call_data: Dict, depth: int = 0):
            if 'calls' in call_data:
                for call in call_data['calls']:
                    internal_tx = {
                        'type': call.get('type', 'CALL'),
                        'from': call.get('from'),
                        'to': call.get('to'),
                        'value': call.get('value', '0x0'),
                        'gas': call.get('gas'),
                        'gasUsed': call.get('gasUsed'),
                        'input': call.get('input', '0x'),
                        'output': call.get('output', '0x'),
                        'depth': depth,
                        'error': call.get('error')
                    }
                    internal_txs.append(internal_tx)
                    
                    # 递归处理嵌套调用
                    extract_calls(call, depth + 1)
        
        if trace_result:
            extract_calls(trace_result)
        
        return internal_txs
    
    def _parse_logs(self, logs: List) -> List[Dict[str, Any]]:
        """
        解析交易logs
        """
        parsed_logs = []
        
        for log in logs:
            parsed_log = {
                'address': log['address'],
                'topics': [topic.hex() for topic in log['topics']],
                'data': log['data'].hex() if hasattr(log['data'], 'hex') else log['data'],
                'blockNumber': log['blockNumber'],
                'transactionHash': log['transactionHash'].hex(),
                'transactionIndex': log['transactionIndex'],
                'blockHash': log['blockHash'].hex(),
                'logIndex': log['logIndex'],
                'removed': log.get('removed', False)
            }
            parsed_logs.append(parsed_log)
        
        return parsed_logs
    
    def get_account_balance(self, address: str) -> int:
        """获取账户余额"""
        return self.w3.eth.get_balance(address)
    
    def fund_account(self, address: str, amount: int):
        """
        为账户充值ETH (仅在测试网络中可用)
        """
        try:
            # 使用anvil_setBalance方法
            self.w3.manager.request_blocking(
                "anvil_setBalance",
                [address, hex(amount)]
            )
            print(f"已为地址 {address} 充值 {amount} wei")
        except Exception as e:
            print(f"充值失败: {str(e)}")

def main():
    # 示例使用
    simulator = EthereumTransactionSimulator()
    
    # 示例参数
    from_address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # Anvil默认账户
    to_address = "0xA5e1a81738259256181f9a0E478188553062D340"    # 另一个Anvil账户
    data = "0x24856bc30000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000000000000000000000010300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000080000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48000000000000000000000000bd22c4c78da827c686217ba17946de11b489855e000000000000000000000000fb4f055095690fac692f6594d54000d2f297f1a700000000000000000000000000000000000000000000000000000002540bc882"  # 简单转账
    value = Web3.to_wei(1, 'ether')  # 1 ETH
    
    # 执行模拟
    result = simulator.simulate_transaction(
        from_address=from_address,
        to_address=to_address,
        data=data,
        value=value
    )
    
    # 输出完整结果到JSON文件
    with open('transaction_result.json', 'a') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n完整结果已保存到 transaction_result.json")

if __name__ == "__main__":
    main()