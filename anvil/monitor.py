# monitor.py
import time
import threading
from typing import Dict, List
from collections import deque
import json

class RealtimeMonitor:
    def __init__(self, simulator):
        self.simulator = simulator
        self.transaction_history = deque(maxlen=1000)
        self.performance_history = deque(maxlen=100)
        self.monitoring = False
        
    def start_monitoring(self, interval: float = 1.0):
        """开始实时监控"""
        self.monitoring = True
        
        def monitor_loop():
            while self.monitoring:
                stats = self.simulator.get_performance_stats()
                self.performance_history.append({
                    'timestamp': time.time(),
                    **stats
                })
                
                # 打印实时统计
                print(f"\r实时统计 - TPS: {stats['transactions_per_second']:.2f}, "
                      f"成功率: {stats['success_rate']:.1f}%, "
                      f"总交易: {stats['total_transactions']}", end='')
                
                time.sleep(interval)
        
        self.monitor_thread = threading.Thread(target=monitor_loop)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()
    
    def on_transaction_complete(self, result):
        """交易完成回调"""
        if result:
            self.transaction_history.append({
                'timestamp': result.timestamp,
                'tx_hash': result.tx_hash,
                'amount': result.amount,
                'gas_used': result.gas_used,
                'status': result.status
            })
    
    def export_results(self, filename: str):
        """导出结果到文件"""
        data = {
            'performance_history': list(self.performance_history),
            'transaction_history': list(self.transaction_history),
            'final_stats': self.simulator.get_performance_stats()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)