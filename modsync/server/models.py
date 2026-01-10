"""
Server models and data structures for ModSync
"""

import os
import hashlib
from datetime import datetime
from typing import Dict, Any, List


class FileModel:
    """Represents a file model with metadata"""
    
    def __init__(self, relpath: str, filepath: str):
        self.relpath = relpath.replace('\\', '/')  # Always use Unix-style paths
        self.filepath = filepath
        self.name = os.path.basename(relpath)
        
        # Load file statistics
        stat = os.stat(filepath)
        self.size = stat.st_size
        self.mtime = stat.st_mtime
        self.hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate SHA256 hash of the file"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(self.filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {self.filepath}: {e}")
            return ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert file model to dictionary"""
        return {
            'relpath': self.relpath,
            'size': self.size,
            'mtime': self.mtime,
            'hash': self.hash,
            'name': self.name
        }


class ServerStats:
    """Server statistics tracker"""
    
    def __init__(self):
        self.requests_count = 0
        self.bytes_sent = 0
        self.start_time = datetime.now()
        self.active_connections = 0
    
    def get_uptime_seconds(self) -> int:
        """Get server uptime in seconds"""
        uptime = datetime.now() - self.start_time
        return int(uptime.total_seconds())
    
    def increment_requests(self):
        """Increment request counter"""
        self.requests_count += 1
    
    def add_bytes_sent(self, bytes_count: int):
        """Add bytes to the sent counter"""
        self.bytes_sent += bytes_count
    
    def increment_connections(self):
        """Increment active connections counter"""
        self.active_connections += 1
    
    def decrement_connections(self):
        """Decrement active connections counter"""
        self.active_connections = max(0, self.active_connections - 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary"""
        return {
            'requests_count': self.requests_count,
            'bytes_sent': self.bytes_sent,
            'uptime_seconds': self.get_uptime_seconds(),
            'start_time': self.start_time.isoformat(),
            'active_connections': self.active_connections
        }