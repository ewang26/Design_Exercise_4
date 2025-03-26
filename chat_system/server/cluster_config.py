import json
from typing import Dict, List

class ClusterConfig:
    def __init__(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        self.servers = self.config.get('servers', [])
        self.election_timeout_min = self.config.get('election_timeout_min', 0.5)
        self.election_timeout_max = self.config.get('election_timeout_max', 1.0)
        self.heartbeat_interval = self.config.get('heartbeat_interval', 0.1)
    
    def get_server_config(self, server_id: int):
        """Get the configuration for a specific server."""
        if server_id < 0 or server_id >= len(self.servers):
            raise ValueError(f"Invalid server ID: {server_id}")
        
        return self.servers[server_id]
    
    def get_peer_addresses(self, server_id: int) -> Dict[str, str]:
        """Get all peer addresses for a specific server."""
        if server_id < 0 or server_id >= len(self.servers):
            raise ValueError(f"Invalid server ID: {server_id}")
        
        peers = {}
        for i, server in enumerate(self.servers):
            if i != server_id:
                peers[f"server{i}"] = f"{server['host']}:{server['raft_port']}"
        
        return peers 