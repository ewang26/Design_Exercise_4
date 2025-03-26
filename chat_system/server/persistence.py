import os
import json
import pickle
from typing import Dict, List, Any, Optional
import threading
import shutil

class PersistentStorage:
    """Provides persistent storage for Raft state and log entries."""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.lock = threading.RLock()
        
        # Create directories if they don't exist
        os.makedirs(os.path.join(storage_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(storage_dir, "state"), exist_ok=True)
        
    def save_raft_state(self, current_term: int, voted_for: Optional[str]) -> None:
        """Save Raft volatile state that must persist across crashes."""
        with self.lock:
            state = {
                "currentTerm": current_term,
                "votedFor": voted_for
            }
            temp_path = os.path.join(self.storage_dir, "state", "raft_state.json.tmp")
            final_path = os.path.join(self.storage_dir, "state", "raft_state.json")
            
            with open(temp_path, 'w') as f:
                json.dump(state, f)
            
            # Atomic rename for crash safety
            shutil.move(temp_path, final_path)
    
    def load_raft_state(self) -> Dict[str, Any]:
        """Load Raft state from disk."""
        with self.lock:
            path = os.path.join(self.storage_dir, "state", "raft_state.json")
            if not os.path.exists(path):
                return {"currentTerm": 0, "votedFor": None}
            
            with open(path, 'r') as f:
                return json.load(f)
    
    def append_log_entries(self, entries: List[Dict[str, Any]]) -> None:
        """Append entries to the Raft log."""
        with self.lock:
            for entry in entries:
                # Each log entry is stored in its own file for crash safety
                # Format: log_[index].pickle
                path = os.path.join(self.storage_dir, "logs", f"log_{entry['index']}.pickle")
                temp_path = f"{path}.tmp"
                
                with open(temp_path, 'wb') as f:
                    pickle.dump(entry, f)
                
                # Atomic rename
                shutil.move(temp_path, path)
    
    def get_log_entry(self, index: int) -> Optional[Dict[str, Any]]:
        """Get a specific log entry by index."""
        with self.lock:
            path = os.path.join(self.storage_dir, "logs", f"log_{index}.pickle")
            if not os.path.exists(path):
                return None
            
            with open(path, 'rb') as f:
                return pickle.load(f)
    
    def get_log_entries_from(self, start_index: int) -> List[Dict[str, Any]]:
        """Get all log entries starting from a specific index."""
        with self.lock:
            entries = []
            index = start_index
            
            while True:
                entry = self.get_log_entry(index)
                if entry is None:
                    break
                entries.append(entry)
                index += 1
            
            return entries
    
    def save_server_state(self, state: Dict[str, Any]) -> None:
        """Save the chat server state (users, messages, etc.)."""
        with self.lock:
            temp_path = os.path.join(self.storage_dir, "state", "server_state.pickle.tmp")
            final_path = os.path.join(self.storage_dir, "state", "server_state.pickle")
            
            with open(temp_path, 'wb') as f:
                pickle.dump(state, f)
            
            # Atomic rename
            shutil.move(temp_path, final_path)
    
    def load_server_state(self) -> Optional[Dict[str, Any]]:
        """Load the chat server state from disk."""
        with self.lock:
            path = os.path.join(self.storage_dir, "state", "server_state.pickle")
            if not os.path.exists(path):
                return None
            
            with open(path, 'rb') as f:
                return pickle.load(f) 