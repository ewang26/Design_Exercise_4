import json
from dataclasses import dataclass

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 8888
DEFAULT_USE_CUSTOM_PROTOCOL = True
DEFAULT_SERVER_DATA_PATH = 'server_data.json'

@dataclass
class ConnectionSettings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    use_custom_protocol: bool = DEFAULT_USE_CUSTOM_PROTOCOL
    server_data_path: str = DEFAULT_SERVER_DATA_PATH

def load_config(config_path: str = "config.json") -> ConnectionSettings:
    """Load connection settings from config file."""
    try:
        with open(config_path) as f:
            print("Loading config from", config_path)
            d = json.load(f)
            return ConnectionSettings(
                host=d.get("host", DEFAULT_HOST),
                port=d.get("port", DEFAULT_PORT),
                use_custom_protocol=d.get("use_custom_protocol", DEFAULT_USE_CUSTOM_PROTOCOL),
                server_data_path=d.get("server_data_path", DEFAULT_SERVER_DATA_PATH)
            )
    except FileNotFoundError:
        print("Config file not found, using default settings")
        return ConnectionSettings()
