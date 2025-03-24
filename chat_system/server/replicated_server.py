import grpc
import json
import os
import threading
import time
import random
from concurrent import futures
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path

from chat_system.common.config import ConnectionSettings
from chat_system.common.command import Command, CommandType
from chat_system.server.server import ChatServer, ChatServicer
from chat_system.proto import chat_pb2, chat_pb2_grpc, raft_pb2, raft_pb2_grpc

class RaftState:
    FOLLOWER = 0
    CANDIDATE = 1
    LEADER = 2

class ReplicatedChatServer:
    def __init__(self, server_id: int, cluster_config: List[Tuple[str, int]], 
                 data_dir: str, config: ConnectionSettings = ConnectionSettings()):
        self.server_id = server_id
        self.cluster_config = cluster_config
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize the underlying chat server
        self.chat_server = ChatServer(config)
        self.chat_server.server_path = self.data_dir / "chat_state.json"
        
        # Raft state
        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.log: List[Tuple[int, Command]] = []  # List of (term, command)
        self.state = RaftState.FOLLOWER
        self.leader_id: Optional[int] = None
        
        # Volatile state
        self.commit_index = 0
        self.last_applied = 0
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}
        
        # Election timeouts
        self.election_timeout = 0.15 + (random.random() * 0.15)  # 150-300ms
        self.last_heartbeat = time.time()
        
        # Threading
        self.running = True
        self.state_lock = threading.Lock()
        self.apply_condition = threading.Condition(self.state_lock)
        
        # Create gRPC server
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        self.host, self.port = cluster_config[server_id]
        
        # Add servicers
        chat_servicer = ChatServicer(self.chat_server)
        chat_pb2_grpc.add_ChatServiceServicer_to_server(chat_servicer, self.server)
        raft_servicer = RaftServicer(self)
        raft_pb2_grpc.add_RaftServiceServicer_to_server(raft_servicer, self.server)
        
        # Create stubs for other servers
        self.peer_stubs: Dict[int, raft_pb2_grpc.RaftServiceStub] = {}
        for i, (host, port) in enumerate(cluster_config):
            if i != server_id:
                channel = grpc.insecure_channel(f'{host}:{port}')
                self.peer_stubs[i] = raft_pb2_grpc.RaftServiceStub(channel)
        
        # Load persistent state
        self.load_persistent_state()
    
    def start(self):
        """Start the server and background threads"""
        # Load chat server state
        self.chat_server.load_state()
        
        # Start gRPC server
        self.server.add_insecure_port(f'{self.host}:{self.port}')
        self.server.start()
        print(f"Server {self.server_id} started on {self.host}:{self.port}")
        
        # Start background threads
        threading.Thread(target=self._election_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._apply_loop, daemon=True).start()
        
        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop the server and save state"""
        self.running = False
        self.save_persistent_state()
        self.chat_server.save_state()
        self.server.stop(0)
    
    def save_persistent_state(self):
        """Save Raft state to disk"""
        state = {
            'current_term': self.current_term,
            'voted_for': self.voted_for,
            'log': [(term, cmd.serialize()) for term, cmd in self.log]
        }
        with open(self.data_dir / 'raft_state.json', 'w') as f:
            json.dump(state, f)
    
    def load_persistent_state(self):
        """Load Raft state from disk"""
        try:
            with open(self.data_dir / 'raft_state.json', 'r') as f:
                state = json.load(f)
                self.current_term = state['current_term']
                self.voted_for = state['voted_for']
                self.log = [(term, Command.deserialize(bytes(cmd))) 
                           for term, cmd in state['log']]
        except FileNotFoundError:
            print(f"No persistent state found for server {self.server_id}")
    
    def _election_loop(self):
        """Monitor for election timeout and start election if needed"""
        while self.running:
            time.sleep(0.01)  # Small sleep to prevent busy waiting
            
            with self.state_lock:
                if (self.state != RaftState.LEADER and 
                    time.time() - self.last_heartbeat > self.election_timeout):
                    self._start_election()
    
    def _start_election(self):
        """Start a new election"""
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.server_id
        self.leader_id = None
        self.save_persistent_state()
        
        last_log_index = len(self.log)
        last_log_term = self.log[-1][0] if self.log else 0
        
        votes_received = 1  # Vote for self
        for peer_id, stub in self.peer_stubs.items():
            try:
                request = raft_pb2.RequestVoteRequest(
                    term=self.current_term,
                    candidate_id=self.server_id,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term
                )
                response = stub.RequestVote(request, timeout=0.1)
                
                if response.vote_granted:
                    votes_received += 1
                elif response.term > self.current_term:
                    self.current_term = response.term
                    self.state = RaftState.FOLLOWER
                    self.voted_for = None
                    self.save_persistent_state()
                    return
                
            except grpc.RpcError:
                continue  # Skip failed RPCs
            
            # If we have a majority
            if votes_received > len(self.cluster_config) / 2:
                self.state = RaftState.LEADER
                self.leader_id = self.server_id
                self.next_index = {i: len(self.log) + 1 for i in self.peer_stubs}
                self.match_index = {i: 0 for i in self.peer_stubs}
                print(f"Server {self.server_id} became leader for term {self.current_term}")
                return
    
    def _heartbeat_loop(self):
        """Send heartbeats if leader"""
        while self.running:
            with self.state_lock:
                if self.state == RaftState.LEADER:
                    self._send_append_entries()
            time.sleep(0.05)  # Send heartbeats every 50ms
    
    def _send_append_entries(self):
        """Send AppendEntries to all peers"""
        for peer_id, stub in self.peer_stubs.items():
            next_idx = self.next_index[peer_id]
            prev_log_index = next_idx - 1
            prev_log_term = self.log[prev_log_index][0] if prev_log_index > 0 else 0
            
            # Get entries to send
            entries = []
            if next_idx <= len(self.log):
                entries = [
                    raft_pb2.LogEntry(
                        term=term,
                        command=cmd.serialize()
                    )
                    for term, cmd in self.log[next_idx-1:]
                ]
            
            try:
                request = raft_pb2.AppendEntriesRequest(
                    term=self.current_term,
                    leader_id=self.server_id,
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    entries=entries,
                    leader_commit=self.commit_index
                )
                
                response = stub.AppendEntries(request, timeout=0.1)
                
                if response.term > self.current_term:
                    self.current_term = response.term
                    self.state = RaftState.FOLLOWER
                    self.voted_for = None
                    self.save_persistent_state()
                    return
                
                if response.success:
                    if entries:
                        self.match_index[peer_id] = prev_log_index + len(entries)
                        self.next_index[peer_id] = self.match_index[peer_id] + 1
                        
                        # Update commit index if possible
                        for n in range(self.commit_index + 1, len(self.log) + 1):
                            if (self.log[n-1][0] == self.current_term and
                                sum(1 for i in self.match_index.values() if i >= n) > len(self.cluster_config) / 2):
                                self.commit_index = n
                                with self.apply_condition:
                                    self.apply_condition.notify()
                else:
                    # Decrement nextIndex and try again
                    self.next_index[peer_id] = max(1, self.next_index[peer_id] - 1)
            
            except grpc.RpcError:
                continue  # Skip failed RPCs
    
    def _apply_loop(self):
        """Apply committed log entries to state machine"""
        while self.running:
            with self.apply_condition:
                while self.commit_index <= self.last_applied and self.running:
                    self.apply_condition.wait()
                
                while self.last_applied < self.commit_index:
                    self.last_applied += 1
                    term, command = self.log[self.last_applied - 1]
                    self._apply_command(command)
    
    def _apply_command(self, command: Command):
        """Apply a command to the chat server"""
        try:
            if command.command_type == CommandType.CREATE_ACCOUNT:
                self.chat_server.account_manager.create_account(
                    command.data['username'],
                    command.data['password']
                )
            elif command.command_type == CommandType.DELETE_ACCOUNT:
                self.chat_server.account_manager.delete_account(
                    command.data['username']
                )
            elif command.command_type == CommandType.SEND_MESSAGE:
                # Add message to recipient's queue
                recipient = self.chat_server.account_manager.get_user(command.data['recipient'])
                if recipient:
                    message = command.data['message']
                    recipient.add_message(message)
            # Add other command types as needed
            
            # Save state after applying command
            self.chat_server.save_state()
            
        except Exception as e:
            print(f"Error applying command {command}: {e}")

class RaftServicer(raft_pb2_grpc.RaftServiceServicer):
    def __init__(self, server: ReplicatedChatServer):
        self.server = server
    
    def RequestVote(self, request, context):
        with self.server.state_lock:
            if request.term < self.server.current_term:
                return raft_pb2.RequestVoteResponse(
                    term=self.server.current_term,
                    vote_granted=False
                )
            
            if request.term > self.server.current_term:
                self.server.current_term = request.term
                self.server.state = RaftState.FOLLOWER
                self.server.voted_for = None
            
            last_log_index = len(self.server.log)
            last_log_term = self.server.log[-1][0] if self.server.log else 0
            
            if (self.server.voted_for is None or self.server.voted_for == request.candidate_id) and \
               (request.last_log_term > last_log_term or \
                (request.last_log_term == last_log_term and request.last_log_index >= last_log_index)):
                self.server.voted_for = request.candidate_id
                self.server.save_persistent_state()
                return raft_pb2.RequestVoteResponse(
                    term=self.server.current_term,
                    vote_granted=True
                )
            
            return raft_pb2.RequestVoteResponse(
                term=self.server.current_term,
                vote_granted=False
            )
    
    def AppendEntries(self, request, context):
        with self.server.state_lock:
            if request.term < self.server.current_term:
                return raft_pb2.AppendEntriesResponse(
                    term=self.server.current_term,
                    success=False
                )
            
            # Update term if needed
            if request.term > self.server.current_term:
                self.server.current_term = request.term
                self.server.state = RaftState.FOLLOWER
                self.server.voted_for = None
                self.server.save_persistent_state()
            
            self.server.last_heartbeat = time.time()
            self.server.leader_id = request.leader_id
            
            # Check previous log entry
            if request.prev_log_index > 0:
                if len(self.server.log) < request.prev_log_index:
                    return raft_pb2.AppendEntriesResponse(
                        term=self.server.current_term,
                        success=False,
                        conflict_index=len(self.server.log)
                    )
                
                if self.server.log[request.prev_log_index - 1][0] != request.prev_log_term:
                    return raft_pb2.AppendEntriesResponse(
                        term=self.server.current_term,
                        success=False,
                        conflict_index=request.prev_log_index - 1
                    )
            
            # Process new entries
            for i, entry in enumerate(request.entries):
                index = request.prev_log_index + i + 1
                if index <= len(self.server.log):
                    if self.server.log[index - 1][0] != entry.term:
                        del self.server.log[index - 1:]
                        self.server.log.append((entry.term, Command.deserialize(entry.command)))
                else:
                    self.server.log.append((entry.term, Command.deserialize(entry.command)))
            
            # Update commit index
            if request.leader_commit > self.server.commit_index:
                self.server.commit_index = min(request.leader_commit, len(self.server.log))
                with self.server.apply_condition:
                    self.server.apply_condition.notify()
            
            return raft_pb2.AppendEntriesResponse(
                term=self.server.current_term,
                success=True
            ) 