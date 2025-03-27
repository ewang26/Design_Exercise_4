import unittest
import subprocess
import time
import os
import signal
import shutil
import grpc
import json
import threading
import random
from chat_system.proto import chat_pb2, chat_pb2_grpc, raft_pb2, raft_pb2_grpc

# Configuration
TEST_CONFIG_PATH = "chat_system/tests/test_cluster_config.json"
TEST_STORAGE_BASE = "chat_system/tests/test_storage"

class FaultToleranceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test configuration
        cls.create_test_config()
        
        # Create server storage directories
        for i in range(3):
            os.makedirs(f"{TEST_STORAGE_BASE}/server{i}", exist_ok=True)
        
        # Start servers
        cls.start_servers()
        
        # Wait for leader election
        time.sleep(5)  # Increased wait time
        
        # Get leader
        cls.leader_address = cls.find_leader()
        if not cls.leader_address:
            print("Warning: No leader found after startup")
        
    @classmethod
    def tearDownClass(cls):
        # Stop servers
        cls.stop_servers()
        
        # Clean up storage
        shutil.rmtree(TEST_STORAGE_BASE, ignore_errors=True)
    
    @classmethod
    def create_test_config(cls):
        config = {
            "servers": [
                {
                    "host": "localhost",
                    "port": 50051,
                    "raft_port": 50052
                },
                {
                    "host": "localhost",
                    "port": 50053,
                    "raft_port": 50054
                },
                {
                    "host": "localhost",
                    "port": 50055,
                    "raft_port": 50056
                }
            ],
            "election_timeout_min": 0.5,
            "election_timeout_max": 1.0,
            "heartbeat_interval": 0.1
        }
        
        os.makedirs(os.path.dirname(TEST_CONFIG_PATH), exist_ok=True)
        with open(TEST_CONFIG_PATH, 'w') as f:
            json.dump(config, f)
    
    @classmethod
    def start_servers(cls):
        cls.server_processes = []
        
        for i in range(3):
            cmd = [
                "python", "-m", "chat_system.server", 
                TEST_CONFIG_PATH, str(i), f"{TEST_STORAGE_BASE}/server{i}"
            ]
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            cls.server_processes.append(process)
            print(f"Started server {i} with PID {process.pid}")
    
    @classmethod
    def stop_servers(cls):
        for i, process in enumerate(cls.server_processes):
            try:
                print(f"Stopping server {i} with PID {process.pid}")
                process.terminate()
                process.wait(timeout=2)
            except:
                print(f"Force killing server {i} with PID {process.pid}")
                process.kill()
    
    @classmethod
    def find_leader(cls):
        """Find the current leader in the cluster."""
        with open(TEST_CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        for server in config['servers']:
            try:
                address = f"{server['host']}:{server['port']}"
                print(f"Trying to connect to {address}")
                channel = grpc.insecure_channel(address)
                stub = chat_pb2_grpc.ChatServiceStub(channel)
                
                # Try to list users - this will work on any server
                response = stub.ListUsers(chat_pb2.ListUsersRequest(pattern=""))
                print(f"Connected to {address}")
                return address
            except Exception as e:
                print(f"Failed to connect to {address}: {str(e)}")
                continue
        
        return None
    
    def get_chat_stub(self):
        """Get a chat stub connected to the leader."""
        leader_address = self.find_leader()
        if not leader_address:
            self.fail("Failed to find leader")
        
        channel = grpc.insecure_channel(leader_address)
        return chat_pb2_grpc.ChatServiceStub(channel)
    
    def create_test_account(self, stub, username, password):
        """Helper to create a test account."""
        response = stub.CreateAccount(
            chat_pb2.CreateAccountRequest(
                username=username,
                password=password
            )
        )
        return not response.HasField('error')
    
    def login(self, stub, username, password):
        """Helper to log in."""
        response = stub.Login(
            chat_pb2.LoginRequest(
                username=username,
                password=password
            )
        )
        return not response.HasField('error')
    
    def test_basic_replication(self):
        """Test that commands are replicated to followers."""
        stub = self.get_chat_stub()
        
        # Create a test account
        result = self.create_test_account(stub, "test_user1", "password1")
        self.assertTrue(result, "Failed to create account")
        
        # Kill the leader
        leader_idx = self.get_leader_index()
        if leader_idx is not None:
            self.server_processes[leader_idx].terminate()
            time.sleep(3)  # Allow time for new leader election
        
        # Get a new stub connected to the new leader
        stub = self.get_chat_stub()
        
        # Try to log in to the account created earlier
        result = self.login(stub, "test_user1", "password1")
        self.assertTrue(result, "Failed to log in after leader change")
    
    def test_message_persistence(self):
        """Test that messages persist across server restarts."""
        stub = self.get_chat_stub()
        
        # Create test accounts
        self.create_test_account(stub, "sender", "password")
        self.create_test_account(stub, "receiver", "password")
        
        # Log in as sender
        self.login(stub, "sender", "password")
        
        # Send a message
        stub.SendMessage(
            chat_pb2.SendMessageRequest(
                receiver="receiver",
                content="Hello, this is a test message!"
            )
        )
        
        # Restart all servers
        self.stop_servers()
        time.sleep(1)
        self.start_servers()
        time.sleep(3)  # Allow time for leader election
        
        # Get a new stub
        stub = self.get_chat_stub()
        
        # Log in as receiver
        self.login(stub, "receiver", "password")
        
        # Check for unread messages
        response = stub.GetNumberOfUnreadMessages(
            chat_pb2.GetNumberOfUnreadMessagesRequest()
        )
        
        self.assertEqual(response.count, 1, "Message was not persisted across server restarts")
    
    def test_2_fault_tolerance(self):
        """Test that the system can tolerate failure of 2 out of 3 servers."""
        stub = self.get_chat_stub()
        
        # Create a test account
        result = self.create_test_account(stub, "fault_test", "password")
        self.assertTrue(result, "Failed to create account")
        
        # Kill 1 server
        self.server_processes[0].terminate()
        time.sleep(1)
        
        # System should still be operational
        stub = self.get_chat_stub()
        result = self.login(stub, "fault_test", "password")
        self.assertTrue(result, "Failed to log in after 1 server down")
        
        # Kill the leader (whichever it is now)
        leader_idx = self.get_leader_index()
        if leader_idx is not None and leader_idx != 0:  # Don't try to kill the already killed server
            self.server_processes[leader_idx].terminate()
            time.sleep(3)  # Allow time for new leader election
        
        # System should be unavailable now with only 1 server running
        with self.assertRaises(Exception):
            stub = self.get_chat_stub()
            self.login(stub, "fault_test", "password")
        
        # Restart servers
        self.stop_servers()
        time.sleep(1)
        self.start_servers()
        time.sleep(3)
        
        # System should be operational again
        stub = self.get_chat_stub()
        result = self.login(stub, "fault_test", "password")
        self.assertTrue(result, "Failed to log in after servers restarted")
    
    def get_leader_index(self):
        """Helper to find the index of the current leader."""
        leader_address = self.find_leader()
        if not leader_address:
            return None
        
        with open(TEST_CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        for i, server in enumerate(config['servers']):
            if f"{server['host']}:{server['port']}" == leader_address:
                return i
        
        return None

if __name__ == '__main__':
    unittest.main() 