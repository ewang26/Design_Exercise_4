# CS 2620 Client-Server Chat System

This project is a simple client-server chat system. It implements replication using a leader-follower model.

### Configuration
The list of servers is detailed in `distributed_config.json`. This file contains a list of servers, each with an IP address and port number. These are the list of all servers in the distributed system; the client will connect to the first server in the list.

### Running
Generate the gRPC code from the proto file:
```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/chat.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/server.proto
```

Next, set up the configuration file in `distributed_config.json`. Once the configuration file is set up, the server can be started with
```bash
python -m chat_system.server <distributed_config.json> <server_id> <server_data.json>
```
The `server_id` is a 0-indexed integer that represents the server's ID in the distributed system list, while `server_data.json` is the path to the persistent storage for the server.

The client can be started with
```bash
python -m chat_system.client <distributed_config.json>
```

### Tests
The full test suite can be run by:
```bash
python -m unittest discover chat_system/tests
```

Our codebase is organized such that it has the following structure:

# Chat System Project Structure

```
chat_system/
│
├─ setup.py                # Package setup configuration
├─ config.json             # Main configuration file
├─ client_config.json      # Client-specific configuration
├─ server_config.json      # Server-specific configuration
├─ notebook.md             # Engineering notebook
├─ design.md               # Design document
│
├─ client/                 # Client-side code
│  ├─ __init__.py
│  ├─ __main__.py         # Client entry point
│  ├─ client.py           # Client implementation
│  └─ gui.py              # GUI implementation
│
├─ server/                 # Server-side code
│  ├─ __init__.py
│  ├─ __main__.py         # Server entry point
│  ├─ server.py           # Server implementation
│  └─ account_manager.py  # User account management
│
├─ common/                 # Shared code between client and server
│  ├─ __init__.py
│  ├─ config.py           # Configuration loading
│  ├─ security.py         # Password hashing and verification
│  ├─ user.py             # User and Message data models
│  │
│  └─ protocol/           # Protocol implementations
│     ├─ __init__.py
│     ├─ protocol.py      # Base protocol classes
│     ├─ custom_protocol.py # Binary protocol implementation
│     └─ json_protocol.py  # JSON protocol implementation
│
└─ tests/                  # Test suite
   ├─ __init__.py
   ├─ test_protocol.py
   ├─ test_server.py
   └─ test_accountmanager.py
```
