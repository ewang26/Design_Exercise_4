import grpc
import json
import random
import time
from typing import List, Tuple, Optional

from chat_system.common.config import ConnectionSettings
from chat_system.proto import chat_pb2, chat_pb2_grpc
from chat_system.client.client import ChatClient

class ReplicatedChatClient(ChatClient):
    def __init__(self, server_list: List[Tuple[str, int]], config: ConnectionSettings = ConnectionSettings()):
        self.server_list = server_list
        self.current_server = 0
        self.leader_id = None
        
        # Initialize with first server
        config.host, config.port = server_list[self.current_server]
        super().__init__(config)
    
    def _create_channel(self) -> grpc.Channel:
        """Create a gRPC channel with retry and timeout options"""
        return grpc.insecure_channel(
            f"{self.host}:{self.port}",
            options=[
                ('grpc.enable_retries', 1),
                ('grpc.keepalive_timeout_ms', 10000),
                ('grpc.keepalive_time_ms', 5000),
            ]
        )
    
    def _handle_error(self, e: grpc.RpcError) -> bool:
        """Handle gRPC errors, return True if operation should be retried"""
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            # Server is down, try next server
            self.current_server = (self.current_server + 1) % len(self.server_list)
            self.host, self.port = self.server_list[self.current_server]
            self.channel = self._create_channel()
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            return True
        
        elif e.code() == grpc.StatusCode.FAILED_PRECONDITION:
            # Not the leader, redirect to leader if known
            details = e.details().split(';')
            if len(details) == 2 and details[0] == "not leader":
                leader_host, leader_port = details[1].split(':')
                # Find leader in server list
                for i, (host, port) in enumerate(self.server_list):
                    if host == leader_host and str(port) == leader_port:
                        self.current_server = i
                        self.host, self.port = host, port
                        self.channel = self._create_channel()
                        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
                        return True
            return True
        
        return False
    
    def _retry_operation(self, operation, *args, **kwargs):
        """Retry an operation with error handling"""
        max_retries = len(self.server_list) * 2
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                return operation(*args, **kwargs)
            except grpc.RpcError as e:
                retry_count += 1
                if not self._handle_error(e) or retry_count >= max_retries:
                    raise
                time.sleep(0.1 * retry_count)  # Exponential backoff
    
    def create_account(self, username: str, password: str):
        return self._retry_operation(super().create_account, username, password)
    
    def login(self, username: str, password: str):
        return self._retry_operation(super().login, username, password)
    
    def logout(self):
        return self._retry_operation(super().logout)
    
    def delete_account(self):
        return self._retry_operation(super().delete_account)
    
    def list_users(self, pattern: str = "", offset: int = 0, limit: int = -1):
        return self._retry_operation(super().list_users, pattern, offset, limit)
    
    def send_message(self, recipient: str, content: str):
        return self._retry_operation(super().send_message, recipient, content)
    
    def get_unread_message_count(self):
        return self._retry_operation(super().get_unread_message_count)
    
    def pop_unread_messages(self, num_messages: int = -1):
        return self._retry_operation(super().pop_unread_messages, num_messages)
    
    def get_read_messages(self, offset: int = 0, limit: int = -1):
        return self._retry_operation(super().get_read_messages, offset, limit)
    
    def delete_messages(self, message_ids: List[int]):
        return self._retry_operation(super().delete_messages, message_ids)
    
    @classmethod
    def from_config(cls, config_path: str) -> 'ReplicatedChatClient':
        """Create a client from a cluster configuration file"""
        with open(config_path) as f:
            server_list = json.load(f)
        return cls(server_list) 