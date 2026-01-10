"""
Server services for ModSync - handles business logic
"""

import os
import json
import hashlib
import threading
from datetime import datetime
from typing import Dict, Any, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from modsync.server.models import FileModel, ServerStats


class FileService:
    """Service for handling file operations"""
    
    def __init__(self, mods_directory: str):
        self.mods_directory = os.path.abspath(mods_directory)
        self.file_hashes = {}
        
        # Create mods directory if it doesn't exist
        os.makedirs(self.mods_directory, exist_ok=True)
        
        # Scan initial files
        self.scan_mods_directory()
    
    def scan_mods_directory(self):
        """Scan the mods directory and compute hashes"""
        for root, dirs, files in os.walk(self.mods_directory):
            for file in files:
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, self.mods_directory)
                self.file_hashes[relpath] = self.calculate_file_hash(filepath)
    
    def calculate_file_hash(self, filepath: str) -> str:
        """Calculate SHA256 hash of a file"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {filepath}: {e}")
            return ""
    
    def get_file_list(self) -> List[Dict[str, Any]]:
        """Generate list of mod files"""
        file_list = []
        for relpath, filehash in self.file_hashes.items():
            filepath = os.path.join(self.mods_directory, relpath)
            if os.path.exists(filepath):
                file_model = FileModel(relpath, filepath)
                file_list.append(file_model.to_dict())
        return sorted(file_list, key=lambda x: x['relpath'])
    
    def setup_file_watcher(self, server_instance):
        """Setup file watcher for monitoring changes"""
        class ModFileHandler(FileSystemEventHandler):
            def __init__(self, server_instance):
                self.server = server_instance
            
            def on_modified(self, event):
                if not event.is_directory and event.src_path.endswith('.jar'):
                    relpath = os.path.relpath(event.src_path, self.server.file_service.mods_directory)
                    self.server.file_service.file_hashes[relpath] = self.server.file_service.calculate_file_hash(event.src_path)
                    print(f"File updated: {relpath}")
            
            def on_created(self, event):
                if not event.is_directory and event.src_path.endswith('.jar'):
                    relpath = os.path.relpath(event.src_path, self.server.file_service.mods_directory)
                    self.server.file_service.file_hashes[relpath] = self.server.file_service.calculate_file_hash(event.src_path)
                    print(f"New file: {relpath}")
            
            def on_deleted(self, event):
                if not event.is_directory:
                    relpath = os.path.relpath(event.src_path, self.server.file_service.mods_directory)
                    if relpath in self.server.file_service.file_hashes:
                        del self.server.file_service.file_hashes[relpath]
                        print(f"File deleted: {relpath}")
        
        self.observer = Observer()
        self.observer.schedule(ModFileHandler(server_instance), self.mods_directory, recursive=True)
        self.observer.start()


class ServerInfoService:
    """Service for providing server information"""
    
    def __init__(self, mods_directory: str, version: str = "1.0.0"):
        self.mods_directory = mods_directory
        self.version = version
    
    def get_server_info(self, stats: ServerStats, file_service: FileService) -> Dict[str, Any]:
        """Get server information"""
        return {
            'version': self.version,
            'mods_count': len(file_service.file_hashes),
            'uptime_seconds': stats.get_uptime_seconds(),
            'requests_served': stats.requests_count,
            'bytes_sent_total': stats.bytes_sent,
            'mods_directory': self.mods_directory,
            'server_time': datetime.now().isoformat(),
            'active_connections_avg': stats.active_connections
        }