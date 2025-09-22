import re
from typing import Dict, Any, Optional, Tuple, List
from evmdasm import EvmBytecode
import json

class PayableFallbackDetector:
    def __init__(self, simulate_tx_func):
        """
        初始化检测器
        
        Args:
            simulate_tx_func: 您现有的交易模拟函数
        """
        self.simulate_tx = simulate_tx_func

    def analyze_bytecode_structure(self, bytecode: str) -> Dict[str, Any]:
        """
        使用evmdasm分析字节码结构
        
        Args:
            bytecode: 合约字节码 (hex string)
            
        Returns:
            Dict: 分析结果
        """
        try:
            # 移除0x前缀
            clean_bytecode = bytecode.replace('0x', '')
            
            # 使用evmdasm反汇编
            evm = EvmBytecode(clean_bytecode)
            disassembly = evm.disassemble()
            
            analysis = {
                "has_fallback": False,
                "has_receive": False,
                "is_payable": False,
                "function_selectors": [],
                "jump_destinations": [],
                "callvalue_checks": [],
                "calldatasize_checks": []
            }
            
            # 分析指令序列
            instructions = list(disassembly)
            
            # 查找函数选择器和跳转目标
            for i, instr in enumerate(instructions):
                # 收集跳转目标
                if instr.name == 'JUMPDEST':
                    analysis["jump_destinations"].append(instr.address)
                
                # 检查CALLVALUE相关操作
                if instr.name == 'CALLVALUE':
                    analysis["callvalue_checks"].append({
                        "address": instr.address,
                        "next_instructions": [instructions[j].name for j in range(i+1, min(i+5, len(instructions)))]
                    })
                
                # 检查CALLDATASIZE相关操作
                if instr.name == 'CALLDATASIZE':
                    analysis["calldatasize_checks"].append({
                        "address": instr.address,
                        "next_instructions": [instructions[j].name for j in range(i+1, min(i+5, len(instructions)))]
                    })
                
                # 查找函数选择器模式 (PUSH4 + EQ)
                if (instr.name == 'PUSH4' and i + 1 < len(instructions) and 
                    instructions[i + 1].name == 'EQ'):
                    selector = instr.operand
                    analysis["function_selectors"].append(selector)
            
            # 分析fallback和receive函数
            analysis.update(self._detect_fallback_receive_patterns(instructions))
            
            return analysis
            
        except Exception as e:
            return {"error": str(e)}

    def _detect_fallback_receive_patterns(self, instructions: List) -> Dict[str, bool]:
        """
        检测fallback和receive函数的模式
        
        Args:
            instructions: 反汇编指令列表
            
        Returns:
            Dict: 检测结果
        """
        result = {
            "has_fallback": False,
            "has_receive": False,
            "is_payable": True  # 默认假设是payable，除非找到明确的非payable模式
        }
        
        # 转换为指令名称序列以便模式匹配
        instr_sequence = [instr.name for instr in instructions]
        instr_str = ' '.join(instr_sequence)
        
        # 检测fallback函数模式
        # 模式1: CALLDATASIZE ISZERO (检查calldata是否为空)
        if 'CALLDATASIZE ISZERO' in instr_str:
            result["has_fallback"] = True
        
        # 模式2: CALLDATASIZE DUP1 ISZERO (更复杂的calldata检查)
        if 'CALLDATASIZE DUP1 ISZERO' in instr_str:
            result["has_fallback"] = True
        
        # 检测receive函数模式
        # 模式: CALLVALUE ISZERO ISZERO (检查msg.value > 0)
        if 'CALLVALUE ISZERO ISZERO' in instr_str:
            result["has_receive"] = True
        
        # 检测非payable模式
        # 模式: CALLVALUE DUP1 ISZERO PUSH2 ... JUMPI (如果有msg.value就跳转到revert)
        non_payable_patterns = [
            'CALLVALUE DUP1 ISZERO PUSH2',
            'CALLVALUE ISZERO PUSH2',
            'CALLVALUE DUP1 ISZERO PUSH1'
        ]
        
        for pattern in non_payable_patterns:
            if pattern in instr_str:
                # 进一步检查是否跳转到revert
                pattern_index = instr_str.find(pattern)
                if pattern_index != -1:
                    # 查看后续指令是否有JUMPI followed by REVERT
                    remaining = instr_str[pattern_index:]
                    if 'JUMPI' in remaining and 'REVERT' in remaining:
                        result["is_payable"] = False
                        break
        
        return result

    def static_analysis(self, bytecode: str) -> Dict[str, Any]:
        """
        静态分析主函数
        
        Args:
            bytecode: 合约字节码 (hex string)
            
        Returns:
            Dict: 静态分析结果
        """
        # 基础字节码结构分析
        structure_analysis = self.analyze_bytecode_structure(bytecode)
        
        if "error" in structure_analysis:
            return {"error": structure_analysis["error"]}
        
        # 综合判断
        has_fallback_or_receive = (
            structure_analysis.get("has_fallback", False) or 
            structure_analysis.get("has_receive", False)
        )
        
        is_payable = structure_analysis.get("is_payable", False)
        
        # 额外的启发式检查
        heuristic_checks = self._heuristic_payable_checks(bytecode)
        
        return {
            "structure_analysis": structure_analysis,
            "heuristic_checks": heuristic_checks,
            "has_fallback_function": has_fallback_or_receive,
            "appears_payable": is_payable and heuristic_checks["likely_payable"],
            "confidence_score": self._calculate_confidence_score(structure_analysis, heuristic_checks)
        }

    def _heuristic_payable_checks(self, bytecode: str) -> Dict[str, Any]:
        """
        启发式检查是否为payable
        
        Args:
            bytecode: 合约字节码 (hex string)
            
        Returns:
            Dict: 启发式检查结果
        """
        clean_bytecode = bytecode.replace('0x', '').upper()
        
        checks = {
            "has_balance_operation": False,
            "has_transfer_operation": False,
            "has_call_with_value": False,
            "likely_payable": True
        }
        
        # 检查是否有余额相关操作
        balance_opcodes = ['31']  # BALANCE
        for opcode in balance_opcodes:
            if opcode in clean_bytecode:
                checks["has_balance_operation"] = True
                break
        
        # 检查是否有转账相关操作
        transfer_opcodes = ['F1', 'F2', 'F4']  # CALL, CALLCODE, DELEGATECALL
        for opcode in transfer_opcodes:
            if opcode in clean_bytecode:
                checks["has_call_with_value"] = True
                break
        
        # 检查明确的非payable revert模式
        # 寻找 CALLVALUE ISZERO 后面紧跟 PUSH + JUMPI 的模式
        non_payable_pattern = r'34158061[0-9A-F]{4}57'  # CALLVALUE ISZERO DUP1 PUSH2 addr JUMPI
        if re.search(non_payable_pattern, clean_bytecode):
            checks["likely_payable"] = False
        
        return checks

    def _calculate_confidence_score(self, structure_analysis: Dict, heuristic_checks: Dict) -> float:
        """
        计算置信度分数
        
        Args:
            structure_analysis: 结构分析结果
            heuristic_checks: 启发式检查结果
            
        Returns:
            float: 置信度分数 (0-1)
        """
        score = 0.0
        
        # 如果有明确的fallback或receive函数
        if structure_analysis.get("has_fallback") or structure_analysis.get("has_receive"):
            score += 0.4
        
        # 如果分析显示是payable
        if structure_analysis.get("is_payable"):
            score += 0.3
        
        # 启发式检查加分
        if heuristic_checks.get("likely_payable"):
            score += 0.2
        
        if heuristic_checks.get("has_balance_operation"):
            score += 0.1
        
        return min(score, 1.0)

    def dynamic_test_payable_fallback(self, contract_address: str, test_value: int = 1000000000000000) -> Tuple[bool, Dict]:
        """
        动态测试：通过发送ETH到合约来测试是否有payable fallback
        
        Args:
            contract_address: 合约地址
            test_value: 测试发送的ETH数量 (wei)
            
        Returns:
            Tuple[bool, Dict]: (是否成功接收ETH, 详细结果)
        """
        # 测试1: 发送ETH但不包含data (触发fallback)
        test_tx_fallback = {
            "from_address": "0x0000000000000000000000000000000000000001",
            "to_address": contract_address,
            "value": hex(test_value),
            "inputdata": "0x",
            "gas": "0x5208"
        }
        
        # 测试2: 发送ETH且包含无效的函数选择器 (也会触发fallback)
        test_tx_invalid_selector = {
            "from_address": "0x0000000000000000000000000000000000000001",
            "to_address": contract_address,
            "value": hex(test_value),
            "inputdata": "0xdeadbeef",  # 无效的函数选择器
            "gas": "0x5208"
        }
        
        results = {}
        
        try:
            # 执行测试1
            result1 = self.simulate_tx(test_tx_fallback)
            results["empty_data_test"] = {
                "success": result1.get("success", False),
                "balance_change": result1.get("balance_change", {}),
                "gas_used": result1.get("gas_used", 0)
            }
            
            # 执行测试2
            result2 = self.simulate_tx(test_tx_invalid_selector)
            results["invalid_selector_test"] = {
                "success": result2.get("success", False),
                "balance_change": result2.get("balance_change", {}),
                "gas_used": result2.get("gas_used", 0)
            }
            
            # 判断是否有payable fallback
            has_payable_fallback = (
                (results["empty_data_test"]["success"] and 
                 results["empty_data_test"]["balance_change"].get(contract_address, 0) > 0) or
                (results["invalid_selector_test"]["success"] and 
                 results["invalid_selector_test"]["balance_change"].get(contract_address, 0) > 0)
            )
            
            return has_payable_fallback, results
            
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
        
        # 静态分析
        static_result = self.static_analysis(bytecode)
        
        if "error" in static_result:
            result["static_analysis"] = {"error": static_result["error"]}
            result["reasoning"].append(f"Static analysis failed: {static_result['error']}")
            return result
        
        result["static_analysis"] = static_result
        
        # 基于静态分析的初步判断（保守策略）
        if not static_result.get("has_fallback_function", False):
            result["reasoning"].append("No fallback function detected in bytecode")
            return result
        
        if not static_result.get("appears_payable", False):
            result["reasoning"].append("Static analysis suggests non-payable fallback")
            return result
        
        # 如果静态分析通过，进行动态测试
        if contract_address:
            dynamic_success, dynamic_result = self.dynamic_test_payable_fallback(contract_address)
            result["dynamic_analysis"] = {
                "test_successful": dynamic_success,
                "details": dynamic_result
            }
            
            if dynamic_success:
                result["has_payable_fallback"] = True
                result["confidence"] = 0.95
                result["reasoning"].append("Dynamic test confirmed payable fallback function")
            else:
                result["confidence"] = static_result.get("confidence_score", 0.0) * 0.5
                result["reasoning"].append("Static analysis suggests payable fallback, but dynamic test failed")
        else:
            # 仅基于静态分析
            if static_result.get("confidence_score", 0.0) > 0.7:
                result["has_payable_fallback"] = True
                result["confidence"] = static_result["confidence_score"] * 0.8  # 降低置信度因为没有动态验证
                result["reasoning"].append("High confidence static analysis suggests payable fallback")
            else:
                result["confidence"] = static_result["confidence_score"] * 0.6
                result["reasoning"].append("Low confidence static analysis, dynamic test recommended")
        
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
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Reasoning: {result['reasoning']}")
    
    # 详细的静态分析结果
    if 'static_analysis' in result:
        static = result['static_analysis']
        print(f"Structure analysis: {static.get('structure_analysis', {})}")
    
    return result