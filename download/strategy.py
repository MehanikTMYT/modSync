class DownloadStrategy:
    """Стратегии скачивания файлов"""
    
    @staticmethod
    def get_optimal_strategy(connection_quality, file_distribution):
        """Автоматическое определение оптимальной стратегии на основе скорости и распределения файлов"""
        strategy = {
            'name': 'adaptive_auto',
            'description': 'Авто-оптимальная стратегия',
            'settings': {}
        }
        
        # Анализ распределения файлов
        tiny_files_pct = file_distribution.get('tiny_files_pct', 0)  # <100KB
        huge_files_pct = file_distribution.get('huge_files_pct', 0)  # >10MB
        
        if connection_quality == 'very_slow':
            # Очень медленное соединение - минимум потоков, максимум надежности
            strategy.update({
                'name': 'stable_sequential',
                'description': 'Стабильная последовательная загрузка',
                'settings': {
                    'max_workers': 1,
                    'chunk_size': 8192,
                    'retry_count': 15,  # Больше попыток для очень медленного соединения
                    'retry_delay': 5,
                    'enable_resume': True,
                    'timeout': 120  # Большой таймаут
                }
            })
        
        elif connection_quality == 'slow':
            # Медленное соединение - осторожная параллельность
            strategy.update({
                'name': 'cautious_parallel',
                'description': 'Осторожная параллельная загрузка',
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
            # Среднее соединение - сбалансированная стратегия
            if huge_files_pct > 5:  # Если много больших файлов
                strategy.update({
                    'name': 'balanced_adaptive',
                    'description': 'Сбалансированная адаптивная загрузка',
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
                    'description': 'Оптимизированная для средней скорости',
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
            # Быстрое соединение - максимальная производительность
            if tiny_files_pct > 70:  # Если преобладают мелкие файлы
                strategy.update({
                    'name': 'tiny_files_optimized',
                    'description': 'Оптимизирована для множества мелких файлов',
                    'settings': {
                        'max_workers': 15,
                        'tiny_file_workers': 20,
                        'small_file_workers': 8,
                        'medium_file_workers': 3,
                        'huge_file_workers': 2,
                        'chunk_size': 65536,
                        'retry_count': 2,
                        'enable_progress': False,  # Отключаем прогресс для скорости
                        'timeout': 20
                    }
                })
            else:
                strategy.update({
                    'name': 'fast_balanced',
                    'description': 'Баланс скорости и стабильности',
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
            # Очень быстрое соединение - максимальная производительность
            strategy.update({
                'name': 'max_performance',
                'description': 'Максимальная производительность',
                'settings': {
                    'max_workers': 25,
                    'tiny_file_workers': 30,
                    'small_file_workers': 10,
                    'medium_file_workers': 5,
                    'huge_file_workers': 3,
                    'chunk_size': 262144,
                    'retry_count': 1,
                    'enable_progress': False,
                    'enable_resume': False,  # Не нужно для очень быстрых соединений
                    'timeout': 15
                }
            })
        
        return strategy
    
    @staticmethod
    def get_manual_strategies():
        """Предопределенные ручные стратегии"""
        return {
            'stable_sequential': {
                'name': '✅ Стабильная последовательная',
                'description': 'Максимальная надежность, минимальные ресурсы. Идеально для очень медленного интернета.',
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
                'name': '⚖️ Сбалансированная адаптивная',
                'description': 'Оптимальный баланс скорости и надежности для большинства пользователей.',
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
                'name': '⚡ Быстрая оптимизированная',
                'description': 'Максимальная скорость для быстрого интернета. Риск перегрузки при нестабильном соединении.',
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
                'name': '🎮 Приоритет для игры',
                'description': 'Сначала загружает критические файлы для быстрого старта игры, остальное в фоне.',
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