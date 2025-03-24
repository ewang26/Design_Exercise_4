#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from chat_system.client.replicated_client import ReplicatedChatClient
from chat_system.common.config import ConnectionSettings

def main():
    parser = argparse.ArgumentParser(description="Run a chat client")
    parser.add_argument("--config", type=str, required=True,
                      help="Path to cluster configuration file")
    
    args = parser.parse_args()
    
    try:
        # Create client from config
        client = ReplicatedChatClient.from_config(args.config)
        
        # Start client (this will start the GUI)
        client.start()
        
    except KeyboardInterrupt:
        print("\nShutting down client...")
    except Exception as e:
        print(f"Client error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 