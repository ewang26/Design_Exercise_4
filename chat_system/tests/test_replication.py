import os
import time
import subprocess
import json
import pytest
from typing import List, Optional

def start_server(server_id: int, config_path: str) -> subprocess.Popen:
    """Start a server process."""
    save_path = f"server_data/server_{server_id}.json"
    cmd = ["python", "-m", "chat_system.server", config_path, str(server_id), save_path]
    return subprocess.Popen(cmd)

def stop_server(process: subprocess.Popen):
    """Stop a server process."""
    process.terminate()
    process.wait()

def wait_for_leader(servers: List[subprocess.Popen], timeout: float = 5.0) -> Optional[int]:
    """Wait for a leader to be elected."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        for i, server in enumerate(servers):
            if server.poll() is not None:
                continue
            # Check Raft state for leader status
            try:
                with open(f"server_data/raft_state_{i}.json") as f:
                    state = json.load(f)
                    if state.get("state") == "leader":
                        return i
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        time.sleep(0.1)
    return None

def test_leader_election():
    """Test that a leader is elected when servers start."""
    # Start three servers
    servers = []
    for i in range(3):
        server = start_server(i, "distributed_config.json")
        servers.append(server)
        time.sleep(0.5)  # Give servers time to start

    # Wait for a leader to be elected
    leader_id = wait_for_leader(servers)
    assert leader_id is not None, "No leader was elected"

    # Stop the leader
    stop_server(servers[leader_id])
    servers.pop(leader_id)

    # Wait for a new leader to be elected
    new_leader_id = wait_for_leader(servers)
    assert new_leader_id is not None, "No new leader was elected after leader failure"

    # Clean up
    for server in servers:
        stop_server(server)

def test_replication():
    """Test that operations are replicated to all servers."""
    # Start three servers
    servers = []
    for i in range(3):
        server = start_server(i, "distributed_config.json")
        servers.append(server)
        time.sleep(0.5)  # Give servers time to start

    # Wait for a leader to be elected
    leader_id = wait_for_leader(servers)
    assert leader_id is not None, "No leader was elected"

    # Create a test account on the leader
    # This would be done through the client API in practice
    leader_state_file = f"server_data/raft_state_{leader_id}.json"
    with open(leader_state_file) as f:
        leader_state = json.load(f)
        leader_state["log"].append({
            "term": leader_state["current_term"],
            "command": {
                "type": "add_user",
                "username": "test_user",
                "password": "test_password",
                "salt": "test_salt"
            },
            "index": len(leader_state["log"])
        })
    with open(leader_state_file, "w") as f:
        json.dump(leader_state, f)

    # Wait for replication
    time.sleep(1.0)

    # Verify the account was replicated to all servers
    for i, server in enumerate(servers):
        if i == leader_id:
            continue
        state_file = f"server_data/raft_state_{i}.json"
        with open(state_file) as f:
            state = json.load(f)
            assert len(state["log"]) == len(leader_state["log"]), \
                f"Server {i} log length mismatch"
            assert state["log"][-1]["command"]["username"] == "test_user", \
                f"Server {i} missing replicated account"

    # Clean up
    for server in servers:
        stop_server(server)

def test_persistence():
    """Test that state persists after server restart."""
    # Start a server
    server = start_server(0, "distributed_config.json")
    time.sleep(0.5)

    # Create a test account
    state_file = "server_data/raft_state_0.json"
    with open(state_file) as f:
        state = json.load(f)
        state["log"].append({
            "term": state["current_term"],
            "command": {
                "type": "add_user",
                "username": "test_user",
                "password": "test_password",
                "salt": "test_salt"
            },
            "index": len(state["log"])
        })
    with open(state_file, "w") as f:
        json.dump(state, f)

    # Stop the server
    stop_server(server)

    # Start the server again
    server = start_server(0, "distributed_config.json")
    time.sleep(0.5)

    # Verify the state was restored
    with open(state_file) as f:
        restored_state = json.load(f)
        assert len(restored_state["log"]) == len(state["log"]), \
            "State not restored after restart"
        assert restored_state["log"][-1]["command"]["username"] == "test_user", \
            "Account not restored after restart"

    # Clean up
    stop_server(server)

def test_fault_tolerance():
    """Test that the system continues to function with server failures."""
    # Start three servers
    servers = []
    for i in range(3):
        server = start_server(i, "distributed_config.json")
        servers.append(server)
        time.sleep(0.5)

    # Wait for a leader to be elected
    leader_id = wait_for_leader(servers)
    assert leader_id is not None, "No leader was elected"

    # Create a test account
    leader_state_file = f"server_data/raft_state_{leader_id}.json"
    with open(leader_state_file) as f:
        state = json.load(f)
        state["log"].append({
            "term": state["current_term"],
            "command": {
                "type": "add_user",
                "username": "test_user",
                "password": "test_password",
                "salt": "test_salt"
            },
            "index": len(state["log"])
        })
    with open(leader_state_file, "w") as f:
        json.dump(state, f)

    # Wait for replication
    time.sleep(1.0)

    # Stop a follower
    follower_id = (leader_id + 1) % 3
    stop_server(servers[follower_id])
    servers.pop(follower_id)

    # Create another account
    with open(leader_state_file) as f:
        state = json.load(f)
        state["log"].append({
            "term": state["current_term"],
            "command": {
                "type": "add_user",
                "username": "test_user2",
                "password": "test_password2",
                "salt": "test_salt2"
            },
            "index": len(state["log"])
        })
    with open(leader_state_file, "w") as f:
        json.dump(state, f)

    # Wait for replication
    time.sleep(1.0)

    # Restart the follower
    server = start_server(follower_id, "distributed_config.json")
    servers.append(server)
    time.sleep(1.0)

    # Verify the follower caught up
    follower_state_file = f"server_data/raft_state_{follower_id}.json"
    with open(follower_state_file) as f:
        follower_state = json.load(f)
        assert len(follower_state["log"]) == len(state["log"]), \
            "Follower did not catch up after restart"
        assert follower_state["log"][-1]["command"]["username"] == "test_user2", \
            "Follower missing replicated account"

    # Clean up
    for server in servers:
        stop_server(server)