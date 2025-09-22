import re
from typing import Dict, Any, Optional, Tuple
from eth_utils import to_hex, to_bytes
import json

class PayableFallbackDetector:
    def __init__(self, simulate_tx_func):
        """
        初始化检测器
        
        Args:
            simulate_tx_func: 您现有的交易模拟函数
        """
        self.simulate_tx = simulate_tx_func
        
        # Solidity编译器生成的常见模式
        self.fallback_patterns = [
            # 检查calldata长度为0的模式 (CALLDATASIZE ISZERO)
            r'36600081',  # CALLDATASIZE PUSH1 0x00 DUP2
            r'366000',    # CALLDATASIZE PUSH1 0x00
            r'36158015',  # CALLDATASIZE ISZERO DUP1 ISZERO
            r'3615',      # CALLDATASIZE ISZERO
        ]
        
        # receive函数的特征模式 (检查msg.value > 0)
        self.receive_patterns = [
            r'34158015',  # CALLVALUE ISZERO DUP1 ISZERO
            r'3415',      # CALLVALUE ISZERO
            r'34600181',  # CALLVALUE PUSH1 0x01 DUP2
        ]

    def has_fallback_bytecode_pattern(self, bytecode: str) -> bool:
        """
        静态分析：检查字节码中是否包含fallback函数的特征模式
        
        Args:
            bytecode: 合约字节码 (hex string)
            
        Returns:
            bool: 是否检测到fallback模式
        """
        # 移除0x前缀并转为大写
        clean_bytecode = bytecode.replace('0x', '').upper()
        
        # 检查是否有fallback或receive函数的模式
        for pattern in self.fallback_patterns + self.receive_patterns:
            if re.search(pattern.upper(), clean_bytecode):
                return True
                
        return False

    def has_payable_modifier_pattern(self, bytecode: str) -> bool:
        """
        检查是否有payable修饰符的字节码模式
        
        Args:
            bytecode: 合约字节码 (hex string)
            
        Returns:
            bool: 是否检测到payable模式
        """
        clean_bytecode = bytecode.replace('0x', '').upper()
        
        # payable函数通常不会在开始就revert CALLVALUE
        # 非payable函数会有 CALLVALUE DUP1 ISZERO PUSH2 ... JUMPI 的模式
        non_payable_pattern = r'34801561[0-9A-F]{4}57'  # CALLVALUE DUP1 ISZERO PUSH2 addr JUMPI
        
        # 如果找到非payable模式，说明不是payable
        if re.search(non_payable_pattern, clean_bytecode):
            return False
            
        return True

    def dynamic_test_payable_fallback(self, contract_address: str, test_value: int = 1000000000000000) -> Tuple[bool, Dict]:
        """
        动态测试：通过发送ETH到合约来测试是否有payable fallback
        
        Args:
            contract_address: 合约地址
            test_value: 测试发送的ETH数量 (wei)
            
        Returns:
            Tuple[bool, Dict]: (是否成功接收ETH, 详细结果)
        """
        # 构造测试交易 - 发送ETH但不包含data
        test_tx = {
            "from_address": "0x0000000000000000000000000000000000000001",  # 测试地址
            "to_address": contract_address,
            "value": hex(test_value),
            "inputdata": "0x",  # 空data触发fallback
            "gas": "0x5208"  # 21000 gas
        }
        
        try:
            result = self.simulate_tx(test_tx)
            
            # 检查交易是否成功且合约余额增加
            success = (
                result.get("success", False) and 
                result.get("balance_change", {}).get(contract_address, 0) > 0
            )
            
            return success, result
            
        except Exception as e:
            return False, {"error": str(e)}

    def detect_payable_fallback(self, bytecode: str, contract_address: Optional[str] = None) -> Dict[str, Any]:
        """
        主检测函数：结合静态和动态分析检测payable fallback函数
        
        Args:
            bytecode: 合约字节码 (hex string)
            contract_address: 合约地址 (可选，用于动态测试)
            
        Returns:
            Dict: 检测结果
        """
        result = {
            "has_payable_fallback": False,
            "confidence": 0.0,
            "static_analysis": {},
            "dynamic_analysis": {},
            "reasoning": []
        }
        
        # 第一步：静态分析 - 检查是否有fallback函数
        has_fallback_pattern = self.has_fallback_bytecode_pattern(bytecode)
        has_payable_pattern = self.has_payable_modifier_pattern(bytecode)
        
        result["static_analysis"] = {
            "has_fallback_pattern": has_fallback_pattern,
            "has_payable_pattern": has_payable_pattern
        }
        
        # 如果静态分析显示没有fallback模式，直接返回False（低FP策略）
        if not has_fallback_pattern:
            result["reasoning"].append("No fallback function pattern detected in bytecode")
            return result
            
        # 如果静态分析显示有明确的非payable模式，返回False
        if not has_payable_pattern:
            result["reasoning"].append("Non-payable modifier pattern detected")
            return result
            
        # 第二步：动态测试（如果提供了合约地址）
        if contract_address:
            dynamic_success, dynamic_result = self.dynamic_test_payable_fallback(contract_address)
            result["dynamic_analysis"] = {
                "test_successful": dynamic_success,
                "details": dynamic_result
            }
            
            if dynamic_success:
                result["has_payable_fallback"] = True
                result["confidence"] = 0.9
                result["reasoning"].append("Dynamic test confirmed payable fallback function")
            else:
                result["reasoning"].append("Dynamic test failed - contract rejected ETH transfer")
        else:
            # 仅基于静态分析的保守判断
            if has_fallback_pattern and has_payable_pattern:
                result["has_payable_fallback"] = True
                result["confidence"] = 0.6  # 较低置信度，因为没有动态验证
                result["reasoning"].append("Static analysis suggests payable fallback, but no dynamic verification")
            
        return result

# 使用示例
def example_usage():
    # 假设您已有的simulate_tx函数
    def your_simulate_tx(tx_data):
        # 您的实现
        pass
    
    # 创建检测器
    detector = PayableFallbackDetector(your_simulate_tx)
    
    # 检测示例
    bytecode = "0x608060405234801561001057600080fd5b50..."
    contract_address = "0x1234567890123456789012345678901234567890"
    
    result = detector.detect_payable_fallback(bytecode, contract_address)
    
    print(f"Has payable fallback: {result['has_payable_fallback']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Reasoning: {result['reasoning']}")
    
    return result