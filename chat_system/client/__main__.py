import argparse
from .client import ChatClient
from ..common.distributed import load_config

def main():
    parser = argparse.ArgumentParser(prog='Chat Client')
    parser.add_argument('config_file', type=str, help='Path to the config file')
    parser.add_argument('server_id', type=int, help='The server ID')
    args = parser.parse_args()

    # Read in config file
    config = load_config(args.config_file)

    # Start client
    client = ChatClient(config, args.server_id)
    client.start()

if __name__ == "__main__":
    main()
