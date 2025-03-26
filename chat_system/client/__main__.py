import argparse
import json
import os
import sys
from ..common.config import ConnectionSettings
from .client import ChatClient
from .gui import ChatGUI

def main():
    parser = argparse.ArgumentParser(description='Start the chat client')
    parser.add_argument('--config', default='chat_system/config/cluster_config.json', 
                       help='Path to cluster configuration file')
    
    args = parser.parse_args()
    
    # Load server addresses from the cluster config
    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        sys.exit(1)
        
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Extract server addresses
    servers = []
    for server in config['servers']:
        # We connect to the Raft port for leader discovery
        servers.append(f"{server['host']}:{server['raft_port']}")
    
    # Create GUI
    gui = ChatGUI("Fault-Tolerant Chat Client")
    
    # Create connection settings
    settings = ConnectionSettings()
    settings.servers = servers
    settings.gui = gui
    
    # Create and run client
    client = ChatClient(settings)
    gui.set_client(client)
    gui.start()

if __name__ == "__main__":
    main()
