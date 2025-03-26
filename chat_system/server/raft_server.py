import grpc
import threading
import time
import random
import queue
import pickle
from concurrent import futures
from typing import Dict, List, Optional, Set, Tuple, Any

from ..proto import chat_pb2, chat_pb2_grpc, raft_pb2, raft_pb2_grpc
from .persistence import PersistentStorage
from .server import ChatServicer
from .replicated_chat_servicer import ReplicatedChatServicer

# Constants
HEARTBEAT_INTERVAL = 0.1  # seconds
ELECTION_TIMEOUT_MIN = 0.5  # seconds
ELECTION_TIMEOUT_MAX = 1.0  # seconds


class RaftNode:
    # Server states
    FOLLOWER = 'follower'
    CANDIDATE = 'candidate'
    LEADER = 'leader'

    def __init__(self, server_id: str, server_address: str, peers: Dict[str, str], 
                 storage_dir: str, chat_port: int):
        self.id = server_id
        self.address = server_address
        self.peers = peers  # {server_id: address}
        self.storage = PersistentStorage(storage_dir)
        self.chat_port = chat_port
        
        # Load persistent state
        raft_state = self.storage.load_raft_state()
        self.current_term = raft_state['currentTerm']
        self.voted_for = raft_state['votedFor']
        
        # Volatile state
        self.state = self.FOLLOWER
        self.leader_id = None
        self.votes_received = set()
        
        # Log related
        self.log = []  # Will be loaded by recovery
        self.commit_index = 0
        self.last_applied = 0
        
        # Leader state (reinitialized after election)
        self.next_index = {peer: 1 for peer in self.peers}
        self.match_index = {peer: 0 for peer in self.peers}
        
        # Locks and conditions
        self.state_lock = threading.RLock()
        self.election_timer = None
        self.heartbeat_timer = None
        
        # gRPC server
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        self.raft_servicer = RaftServicer(self)
        raft_pb2_grpc.add_RaftServiceServicer_to_server(self.raft_servicer, self.server)
        
        # Chat server state
        self.server_state = None  # Will be loaded by recovery
        self.chat_servicer = None  # Will be initialized after recovery
        
        # Command application queue (for serializing log application)
        self.apply_queue = queue.Queue()
        self.apply_thread = threading.Thread(target=self._apply_log_entries)
        self.apply_thread.daemon = True
        
        # Recovery on startup
        self._recover_state()
        
    def _recover_state(self):
        """Recover server state from disk."""
        # Load log entries
        self.log = []
        index = 0
        while True:
            entry = self.storage.get_log_entry(index)
            if entry is None:
                break
            self.log.append(entry)
            index += 1
        
        # Initialize last applied to the highest index in the log
        if self.log:
            self.commit_index = 0  # Will be updated by leader
            self.last_applied = 0
        
        # Load server state
        server_state = self.storage.load_server_state()
        if server_state:
            self.server_state = server_state
        else:
            # Initialize new state if none exists
            self.server_state = {
                "users": {},
                "next_message_id": 0,
                "messages": {}
            }
        
        # Initialize chat servicer
        self.chat_servicer = ReplicatedChatServicer(self)
        chat_pb2_grpc.add_ChatServiceServicer_to_server(self.chat_servicer, self.server)
    
    def start(self):
        """Start the Raft node."""
        # Start server
        self.server.add_insecure_port(self.address)
        self.server.start()
        
        # Start log application thread
        self.apply_thread.start()
        
        # Start as follower
        self._become_follower(self.current_term)
        
        print(f"Raft node {self.id} started at {self.address}")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.server.stop(0)
    
    def _reset_election_timer(self):
        """Reset the election timeout."""
        with self.state_lock:
            if self.election_timer:
                self.election_timer.cancel()
            
            timeout = random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)
            self.election_timer = threading.Timer(timeout, self._start_election)
            self.election_timer.daemon = True
            self.election_timer.start()
    
    def _cancel_election_timer(self):
        """Cancel the election timer."""
        with self.state_lock:
            if self.election_timer:
                self.election_timer.cancel()
                self.election_timer = None
    
    def _become_follower(self, term):
        """Transition to follower state."""
        with self.state_lock:
            self.state = self.FOLLOWER
            self.current_term = term
            self.voted_for = None
            self.storage.save_raft_state(self.current_term, self.voted_for)
            
            # Reset election timer
            self._reset_election_timer()
            
            # Cancel heartbeat timer if exists
            if self.heartbeat_timer:
                self.heartbeat_timer.cancel()
                self.heartbeat_timer = None
    
    def _become_candidate(self):
        """Transition to candidate state and start an election."""
        with self.state_lock:
            self.state = self.CANDIDATE
            self.current_term += 1
            self.voted_for = self.id  # Vote for self
            self.votes_received = {self.id}  # Count own vote
            self.storage.save_raft_state(self.current_term, self.voted_for)
            
            # Reset election timer
            self._reset_election_timer()
    
    def _become_leader(self):
        """Transition to leader state."""
        with self.state_lock:
            if self.state != self.CANDIDATE:
                return
                
            self.state = self.LEADER
            self.leader_id = self.id
            
            # Initialize leader state
            last_log_index = len(self.log)
            self.next_index = {peer: last_log_index + 1 for peer in self.peers}
            self.match_index = {peer: 0 for peer in self.peers}
            
            # Cancel election timer
            self._cancel_election_timer()
            
            # Start sending heartbeats
            self._send_heartbeats()
    
    def _start_election(self):
        """Start a leader election."""
        with self.state_lock:
            if self.state == self.LEADER:
                return
            
            self._become_candidate()
            
            # Prepare request
            last_log_index = len(self.log) - 1
            last_log_term = self.log[last_log_index]['term'] if last_log_index >= 0 else 0
            
            request = raft_pb2.RequestVoteRequest(
                term=self.current_term,
                candidateId=self.id,
                lastLogIndex=last_log_index,
                lastLogTerm=last_log_term
            )
            
            # Send RequestVote RPCs to all peers
            for peer_id, peer_addr in self.peers.items():
                threading.Thread(target=self._request_vote, 
                                args=(peer_id, peer_addr, request)).start()
    
    def _request_vote(self, peer_id, peer_addr, request):
        """Send RequestVote RPC to a peer."""
        try:
            channel = grpc.insecure_channel(peer_addr)
            stub = raft_pb2_grpc.RaftServiceStub(channel)
            response = stub.RequestVote(request)
            
            with self.state_lock:
                # If we're no longer a candidate, ignore the response
                if self.state != self.CANDIDATE:
                    return
                
                # If response term is higher, become follower
                if response.term > self.current_term:
                    self._become_follower(response.term)
                    return
                
                # If vote granted and we're still in the same term
                if response.voteGranted and response.term == self.current_term:
                    self.votes_received.add(peer_id)
                    
                    # Check if we have majority
                    if len(self.votes_received) > (len(self.peers) + 1) / 2:
                        self._become_leader()
                
        except Exception as e:
            print(f"Error requesting vote from {peer_id}: {e}")
    
    def _send_heartbeats(self):
        """Send AppendEntries RPCs to all peers as heartbeats."""
        with self.state_lock:
            if self.state != self.LEADER:
                return
            
            # Send AppendEntries RPCs to all peers
            for peer_id, peer_addr in self.peers.items():
                threading.Thread(target=self._send_append_entries, 
                                args=(peer_id, peer_addr)).start()
            
            # Schedule next heartbeat
            self.heartbeat_timer = threading.Timer(HEARTBEAT_INTERVAL, self._send_heartbeats)
            self.heartbeat_timer.daemon = True
            self.heartbeat_timer.start()
    
    def _send_append_entries(self, peer_id, peer_addr):
        """Send AppendEntries RPC to a peer."""
        try:
            with self.state_lock:
                if self.state != self.LEADER:
                    return
                
                next_idx = self.next_index[peer_id]
                prev_log_index = next_idx - 1
                prev_log_term = 0
                
                if prev_log_index >= 0 and prev_log_index < len(self.log):
                    prev_log_term = self.log[prev_log_index]['term']
                
                # Prepare entries to send
                entries = []
                if next_idx <= len(self.log):
                    entries = self.log[next_idx - 1:]
                
                # Convert entries to protobuf format
                entries_pb = []
                for entry in entries:
                    entry_pb = raft_pb2.LogEntry(
                        term=entry['term'],
                        index=entry['index'],
                        data=entry['data'],
                        commandType=entry['commandType']
                    )
                    entries_pb.append(entry_pb)
                
                request = raft_pb2.AppendEntriesRequest(
                    term=self.current_term,
                    leaderId=self.id,
                    prevLogIndex=prev_log_index,
                    prevLogTerm=prev_log_term,
                    entries=entries_pb,
                    leaderCommit=self.commit_index
                )
            
            # Send request outside the lock
            channel = grpc.insecure_channel(peer_addr)
            stub = raft_pb2_grpc.RaftServiceStub(channel)
            response = stub.AppendEntries(request)
            
            with self.state_lock:
                # If we're no longer the leader, ignore the response
                if self.state != self.LEADER:
                    return
                
                # If response term is higher, become follower
                if response.term > self.current_term:
                    self._become_follower(response.term)
                    return
                
                if response.success:
                    # Update nextIndex and matchIndex for successful AppendEntries
                    if entries:
                        self.match_index[peer_id] = entries[-1]['index']
                        self.next_index[peer_id] = self.match_index[peer_id] + 1
                    
                    # Update commit index if needed
                    self._update_commit_index()
                else:
                    # Decrement nextIndex and retry
                    self.next_index[peer_id] = max(1, self.next_index[peer_id] - 1)
                    # Immediately retry with updated indices
                    threading.Thread(target=self._send_append_entries, 
                                    args=(peer_id, peer_addr)).start()
                
        except Exception as e:
            print(f"Error sending AppendEntries to {peer_id}: {e}")
    
    def _update_commit_index(self):
        """Update commit index based on the match indices of followers."""
        with self.state_lock:
            if self.state != self.LEADER:
                return
            
            # For each log entry, check if it's replicated on a majority of servers
            for n in range(self.commit_index + 1, len(self.log) + 1):
                # Count servers that have this entry
                count = 1  # Leader itself
                for peer_id in self.peers:
                    if self.match_index[peer_id] >= n:
                        count += 1
                
                # If majority and term is current term
                idx = n - 1  # Convert to 0-based index
                if count > (len(self.peers) + 1) / 2 and self.log[idx]['term'] == self.current_term:
                    self.commit_index = n
                    # Trigger log application
                    self.apply_queue.put(None)  # Signal to apply commits
    
    def _apply_log_entries(self):
        """Apply committed log entries to the state machine."""
        while True:
            # Wait for signal to apply
            self.apply_queue.get()
            
            with self.state_lock:
                while self.last_applied < self.commit_index:
                    self.last_applied += 1
                    entry = self.log[self.last_applied - 1]
                    
                    # Apply the command to the state machine
                    self._apply_command(entry)
                    
                    # Save state after applying command
                    self.storage.save_server_state(self.server_state)
    
    def _apply_command(self, entry):
        """Apply a log entry to the state machine."""
        try:
            command_type = entry['commandType']
            command_data = entry['data']
            
            # Implement command application based on command type
            if command_type == 'create_account':
                username, password = pickle.loads(command_data)
                self._create_account(username, password)
            elif command_type == 'delete_account':
                username = pickle.loads(command_data)
                self._delete_account(username)
            elif command_type == 'send_message':
                sender, recipient, content = pickle.loads(command_data)
                self._send_message(sender, recipient, content)
            elif command_type == 'delete_messages':
                username, message_ids = pickle.loads(command_data)
                self._delete_messages(username, message_ids)
            
        except Exception as e:
            print(f"Error applying command: {e}")
    
    def append_command(self, command_type, command_data):
        """Append a command to the log and replicate it."""
        with self.state_lock:
            if self.state != self.LEADER:
                # Redirect to leader
                if self.leader_id and self.leader_id in self.peers:
                    leader_addr = self.peers[self.leader_id]
                    return False, f"Not leader, redirect to {leader_addr}"
                return False, "Not leader, and leader unknown"
            
            # Create log entry
            index = len(self.log)
            entry = {
                'term': self.current_term,
                'index': index,
                'data': command_data,
                'commandType': command_type
            }
            
            # Append to log
            self.log.append(entry)
            self.storage.append_log_entries([entry])
            
            # Update own match index for consistency
            self.match_index[self.id] = index
            
            # Replicate to followers
            for peer_id, peer_addr in self.peers.items():
                threading.Thread(target=self._send_append_entries, 
                                args=(peer_id, peer_addr)).start()
            
            return True, None
    
    # State machine operations (these would be called only on commit, not on initial request)
    def _create_account(self, username, password):
        if username not in self.server_state['users']:
            self.server_state['users'][username] = {
                'password': password,
                'messages': {'unread': [], 'read': []}
            }
            return True
        return False
    
    def _delete_account(self, username):
        if username in self.server_state['users']:
            del self.server_state['users'][username]
            return True
        return False
    
    def _send_message(self, sender, recipient, content):
        if recipient in self.server_state['users']:
            msg_id = self.server_state['next_message_id']
            self.server_state['next_message_id'] += 1
            
            message = {
                'id': msg_id,
                'sender': sender,
                'content': content
            }
            
            self.server_state['messages'][msg_id] = message
            self.server_state['users'][recipient]['messages']['unread'].append(msg_id)
            return True
        return False
    
    def _delete_messages(self, username, message_ids):
        if username in self.server_state['users']:
            user = self.server_state['users'][username]
            
            # Remove from unread
            user['messages']['unread'] = [
                msg_id for msg_id in user['messages']['unread'] 
                if msg_id not in message_ids
            ]
            
            # Remove from read
            user['messages']['read'] = [
                msg_id for msg_id in user['messages']['read'] 
                if msg_id not in message_ids
            ]
            
            # Optionally, we could also remove from the global messages dictionary
            # to free up memory if no other user references these messages
            return True
        return False


class RaftServicer(raft_pb2_grpc.RaftServiceServicer):
    def __init__(self, node):
        self.node = node
    
    def RequestVote(self, request, context):
        with self.node.state_lock:
            # If term is outdated, reject vote
            if request.term < self.node.current_term:
                return raft_pb2.RequestVoteResponse(
                    term=self.node.current_term,
                    voteGranted=False
                )
            
            # If term is newer, become follower
            if request.term > self.node.current_term:
                self.node._become_follower(request.term)
            
            # Check if we can vote for this candidate
            can_vote = (self.node.voted_for is None or self.node.voted_for == request.candidateId)
            
            # Check if candidate's log is at least as up-to-date as ours
            last_log_index = len(self.node.log) - 1
            last_log_term = self.node.log[last_log_index]['term'] if last_log_index >= 0 else 0
            
            log_ok = (request.lastLogTerm > last_log_term or 
                     (request.lastLogTerm == last_log_term and 
                      request.lastLogIndex >= last_log_index))
            
            vote_granted = can_vote and log_ok
            
            if vote_granted:
                self.node.voted_for = request.candidateId
                self.node.storage.save_raft_state(self.node.current_term, self.node.voted_for)
                self.node._reset_election_timer()
            
            return raft_pb2.RequestVoteResponse(
                term=self.node.current_term,
                voteGranted=vote_granted
            )
    
    def AppendEntries(self, request, context):
        with self.node.state_lock:
            # If term is outdated, reject
            if request.term < self.node.current_term:
                return raft_pb2.AppendEntriesResponse(
                    term=self.node.current_term,
                    success=False
                )
            
            # If term is newer or we're a candidate, become follower
            if request.term > self.node.current_term or self.node.state == RaftNode.CANDIDATE:
                self.node._become_follower(request.term)
            
            # Always update leader ID and reset election timer
            self.node.leader_id = request.leaderId
            self.node._reset_election_timer()
            
            # Check if log contains an entry at prevLogIndex with prevLogTerm
            success = False
            
            if (request.prevLogIndex == -1 or 
                (request.prevLogIndex < len(self.node.log) and 
                 self.node.log[request.prevLogIndex]['term'] == request.prevLogTerm)):
                success = True
                
                # Now we can process the entries
                new_entries = []
                for entry_pb in request.entries:
                    entry = {
                        'term': entry_pb.term,
                        'index': entry_pb.index,
                        'data': entry_pb.data,
                        'commandType': entry_pb.commandType
                    }
                    new_entries.append(entry)
                
                if new_entries:
                    # Find conflicting entries and delete them
                    conflict_idx = -1
                    for i, entry in enumerate(new_entries):
                        log_idx = entry['index']
                        if log_idx < len(self.node.log):
                            if self.node.log[log_idx]['term'] != entry['term']:
                                conflict_idx = log_idx
                                break
                        else:
                            break
                    
                    if conflict_idx != -1:
                        # Delete conflicting entries and all that follow
                        self.node.log = self.node.log[:conflict_idx]
                    
                    # Append new entries
                    append_start = len(self.node.log)
                    for entry in new_entries[append_start - append_start:]:
                        self.node.log.append(entry)
                    
                    # Persist log to disk
                    self.node.storage.append_log_entries(new_entries[append_start - append_start:])
                
                # Update commit index
                if request.leaderCommit > self.node.commit_index:
                    self.node.commit_index = min(request.leaderCommit, len(self.node.log))
                    # Trigger log application
                    self.node.apply_queue.put(None)
            
            return raft_pb2.AppendEntriesResponse(
                term=self.node.current_term,
                success=success,
                matchIndex=len(self.node.log) - 1
            )
    
    def GetLeader(self, request, context):
        """Return the current leader's ID and address."""
        with self.node.state_lock:
            leader_id = self.node.leader_id if self.node.leader_id else ""
            leader_address = ""
            
            if leader_id:
                if leader_id == self.node.id:
                    leader_address = self.node.address
                elif leader_id in self.node.peers:
                    leader_address = self.node.peers[leader_id]
            
            return raft_pb2.GetLeaderResponse(
                leaderId=leader_id,
                leaderAddress=leader_address
            )
    
    def AddServer(self, request, context):
        """Add a new server to the cluster."""
        with self.node.state_lock:
            if self.node.state != RaftNode.LEADER:
                return raft_pb2.AddServerResponse(
                    success=False,
                    error="Not leader"
                )
            
            # Validate server doesn't already exist
            if request.serverId in self.node.peers:
                return raft_pb2.AddServerResponse(
                    success=False,
                    error=f"Server {request.serverId} already exists"
                )
            
            # Add the server to peers
            self.node.peers[request.serverId] = request.serverAddress
            
            # Initialize next and match indices for the new server
            self.node.next_index[request.serverId] = len(self.node.log) + 1
            self.node.match_index[request.serverId] = 0
            
            # Start replicating to the new server
            threading.Thread(target=self.node._send_append_entries, 
                            args=(request.serverId, request.serverAddress)).start()
            
            return raft_pb2.AddServerResponse(
                success=True,
                error=""
            )
    
    def RemoveServer(self, request, context):
        """Remove a server from the cluster."""
        with self.node.state_lock:
            if self.node.state != RaftNode.LEADER:
                return raft_pb2.RemoveServerResponse(
                    success=False,
                    error="Not leader"
                )
            
            # Validate server exists
            if request.serverId not in self.node.peers:
                return raft_pb2.RemoveServerResponse(
                    success=False,
                    error=f"Server {request.serverId} does not exist"
                )
            
            # Remove the server from peers
            del self.node.peers[request.serverId]
            
            # Remove from next and match indices
            if request.serverId in self.node.next_index:
                del self.node.next_index[request.serverId]
            
            if request.serverId in self.node.match_index:
                del self.node.match_index[request.serverId]
            
            return raft_pb2.RemoveServerResponse(
                success=True,
                error=""
            ) 