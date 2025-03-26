import argparse
from .client import ChatClient
from ..common.distributed import load_config

def main():
    parser = argparse.ArgumentParser(prog='Chat Client')
    parser.add_argument('config_file', type=str, help='Path to the config file')
    args = parser.parse_args()

    # Read in config file
    config = load_config(args.config_file)

    # Start client
    client = ChatClient(config)
    client.start()

if __name__ == "__main__":
    main()
