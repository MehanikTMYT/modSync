"""
Strategy factory for download operations
"""

from modsync.client.download.strategies.sequential_strategy import SequentialStrategy
from modsync.client.download.strategies.adaptive_strategy import AdaptiveStrategy


class StrategyFactory:
    """Factory for creating download strategies"""
    
    @staticmethod
    def create_strategy(strategy_config):
        """Create a strategy instance based on configuration"""
        strategy_name = strategy_config.get('name', '')
        
        if strategy_name in ['stable_sequential', 'cautious_parallel']:
            return SequentialStrategy(strategy_config)
        elif strategy_name in ['balanced_adaptive', 'medium_optimized', 'fast_balanced', 'max_performance', 'tiny_files_optimized', 'gaming_priority']:
            return AdaptiveStrategy(strategy_config)
        else:
            # Default to adaptive strategy
            return AdaptiveStrategy({
                'name': 'balanced_adaptive',
                'settings': {
                    'max_workers': 6,
                    'tiny_file_workers': 8,
                    'small_file_workers': 4,
                    'medium_file_workers': 2,
                    'huge_file_workers': 1,
                    'chunk_size': 32768,
                    'retry_count': 5,
                    'timeout': 45
                }
            })