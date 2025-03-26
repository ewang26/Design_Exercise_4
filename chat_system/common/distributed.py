import json
from dataclasses import dataclass
from typing import List


@dataclass
class ServerConnection:
    host: str
    port: int

@dataclass
class DistributedConfig:
    servers: List[ServerConnection]

def load_config(config_path: str) -> DistributedConfig:
    """Load connection settings from config file."""
    try:
        with open(config_path) as f:
            print("Loading config from", config_path)
            d = json.load(f)
            servers = []
            for server in d["servers"]:
                servers.append(ServerConnection(
                    host=server["host"],
                    port=server["port"]
                ))
            return DistributedConfig(servers=servers)
    except FileNotFoundError:
        print("Config file not found, using default settings")
        return DistributedConfig(servers=[])
