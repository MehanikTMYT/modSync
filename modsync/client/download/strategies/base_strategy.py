"""
Base strategy for download operations
"""


class BaseDownloadStrategy:
    """Base class for download strategies"""
    
    def __init__(self, strategy_config):
        self.config = strategy_config
        self.progress_callback = None
        self.error_callback = None
    
    def set_progress_callback(self, callback):
        """Set progress callback"""
        self.progress_callback = callback
    
    def set_error_callback(self, callback):
        """Set error callback"""
        self.error_callback = callback
    
    def execute_download(self, files_to_download, file_distribution=None):
        """Execute download with this strategy - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement execute_download method")
    
    def _log_info(self, message):
        """Log informational message"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"[STRATEGY] {message}")
    
    def _log_error(self, message):
        """Log error message"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"[ERROR] {message}")