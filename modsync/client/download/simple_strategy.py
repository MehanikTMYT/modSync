"""
Simplified download strategy module for ModSync client
All strategy logic consolidated into a single file to reduce complexity
"""

class DownloadStrategy:
    """Download strategies simplified implementation"""
    
    @staticmethod
    def get_optimal_strategy(connection_quality, file_distribution):
        """Automatic determination of optimal strategy based on connection and file distribution"""
        strategy = {
            'name': 'adaptive_auto',
            'description': 'Auto-optimal strategy',
            'settings': {}
        }
        
        # Analyze file distribution
        tiny_files_pct = file_distribution.get('tiny_files_pct', 0)  # <100KB
        huge_files_pct = file_distribution.get('huge_files_pct', 0)  # >10MB
        
        if connection_quality == 'very_slow':
            # Very slow connection - minimum threads, maximum reliability
            strategy.update({
                'name': 'stable_sequential',
                'description': 'Stable sequential download',
                'settings': {
                    'max_workers': 1,
                    'chunk_size': 8192,
                    'retry_count': 15,  # More attempts for very slow connection
                    'retry_delay': 5,
                    'enable_resume': True,
                    'timeout': 120  # Large timeout
                }
            })
        
        elif connection_quality == 'slow':
            # Slow connection - careful parallelization
            strategy.update({
                'name': 'cautious_parallel',
                'description': 'Cautious parallel download',
                'settings': {
                    'max_workers': 2,
                    'tiny_file_workers': 2,
                    'small_file_workers': 1,
                    'medium_file_workers': 1,
                    'huge_file_workers': 1,
                    'chunk_size': 16384,
                    'retry_count': 10,
                    'retry_delay': 2,
                    'enable_resume': True,
                    'timeout': 60
                }
            })
        
        elif connection_quality == 'medium':
            # Medium connection - balanced strategy
            if huge_files_pct > 5:  # If many large files
                strategy.update({
                    'name': 'balanced_adaptive',
                    'description': 'Balanced adaptive download',
                    'settings': {
                        'max_workers': 4,
                        'tiny_file_workers': 6,
                        'small_file_workers': 3,
                        'medium_file_workers': 2,
                        'huge_file_workers': 1,
                        'chunk_size': 32768,
                        'retry_count': 5,
                        'enable_resume': True,
                        'timeout': 45
                    }
                })
            else:
                strategy.update({
                    'name': 'medium_optimized',
                    'description': 'Optimized for medium speed',
                    'settings': {
                        'max_workers': 6,
                        'tiny_file_workers': 8,
                        'small_file_workers': 4,
                        'medium_file_workers': 2,
                        'huge_file_workers': 1,
                        'chunk_size': 65536,
                        'retry_count': 3,
                        'enable_resume': True,
                        'timeout': 30
                    }
                })
        
        elif connection_quality == 'fast':
            # Fast connection - maximum performance
            if tiny_files_pct > 70:  # If predominantly small files
                strategy.update({
                    'name': 'tiny_files_optimized',
                    'description': 'Optimized for many small files',
                    'settings': {
                        'max_workers': 15,
                        'tiny_file_workers': 20,
                        'small_file_workers': 8,
                        'medium_file_workers': 3,
                        'huge_file_workers': 2,
                        'chunk_size': 65536,
                        'retry_count': 2,
                        'enable_progress': False,  # Disable progress for speed
                        'timeout': 20
                    }
                })
            else:
                strategy.update({
                    'name': 'fast_balanced',
                    'description': 'Speed and stability balance',
                    'settings': {
                        'max_workers': 10,
                        'tiny_file_workers': 12,
                        'small_file_workers': 6,
                        'medium_file_workers': 3,
                        'huge_file_workers': 2,
                        'chunk_size': 131072,
                        'retry_count': 2,
                        'enable_resume': True,
                        'timeout': 25
                    }
                })
        
        elif connection_quality == 'very_fast':
            # Very fast connection - maximum performance
            strategy.update({
                'name': 'max_performance',
                'description': 'Maximum performance',
                'settings': {
                    'max_workers': 25,
                    'tiny_file_workers': 30,
                    'small_file_workers': 10,
                    'medium_file_workers': 5,
                    'huge_file_workers': 3,
                    'chunk_size': 262144,
                    'retry_count': 1,
                    'enable_progress': False,
                    'enable_resume': False,  # Not needed for very fast connections
                    'timeout': 15
                }
            })
        
        return strategy
    
    @staticmethod
    def get_manual_strategies():
        """Predefined manual strategies"""
        return {
            'stable_sequential': {
                'name': '✅ Stable Sequential',
                'description': 'Maximum reliability, minimum resources. Ideal for very slow internet.',
                'default': False,
                'settings': {
                    'max_workers': 1,
                    'chunk_size': 8192,
                    'retry_count': 15,
                    'retry_delay': 5,
                    'enable_resume': True,
                    'timeout': 120
                }
            },
            'balanced_adaptive': {
                'name': '⚖️ Balanced Adaptive',
                'description': 'Optimal balance of speed and reliability for most users.',
                'default': True,
                'settings': {
                    'max_workers': 6,
                    'tiny_file_workers': 8,
                    'small_file_workers': 4,
                    'medium_file_workers': 2,
                    'huge_file_workers': 1,
                    'chunk_size': 32768,
                    'retry_count': 5,
                    'enable_resume': True,
                    'timeout': 45
                }
            },
            'fast_optimized': {
                'name': '⚡ Fast Optimized',
                'description': 'Maximum speed for fast internet. Risk of overload with unstable connection.',
                'default': False,
                'settings': {
                    'max_workers': 15,
                    'tiny_file_workers': 20,
                    'small_file_workers': 8,
                    'medium_file_workers': 4,
                    'huge_file_workers': 2,
                    'chunk_size': 131072,
                    'retry_count': 3,
                    'enable_resume': True,
                    'timeout': 30
                }
            },
            'gaming_priority': {
                'name': '🎮 Gaming Priority',
                'description': 'Downloads critical files first for quick game start, others in background.',
                'default': False,
                'settings': {
                    'critical_workers': 8,
                    'essential_workers': 4,
                    'background_workers': 2,
                    'enable_game_ready_notification': True,
                    'timeout': 60
                }
            }
        }