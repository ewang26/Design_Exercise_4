import time
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

@dataclass
class LogEntry:
    term: int
    command: dict
    index: int

class NodeState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

class RaftNode:
    def __init__(self, node_id: int, config_path: str, data_dir: str):
        self.node_id = node_id
        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.log: List[LogEntry] = []
        self.commit_index = 0
        self.last_applied = 0
        
        # Leader state
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}
        
        # Election timeout
        self.election_timeout = 150  # milliseconds
        self.last_heartbeat = time.time()
        
        # Heartbeat interval
        self.heartbeat_interval = 50  # milliseconds
        
        # Load config
        with open(config_path) as f:
            config = json.load(f)
            self.servers = config["servers"]
            self.num_servers = len(self.servers)
        
        # Setup data directory
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Load persistent state
        self.load_state()
        
        # Initialize leader state
        for i in range(self.num_servers):
            if i != self.node_id:
                self.next_index[i] = len(self.log)
                self.match_index[i] = 0

    def load_state(self):
        """Load persistent state from disk."""
        state_file = os.path.join(self.data_dir, f"raft_state_{self.node_id}.json")
        try:
            with open(state_file) as f:
                state = json.load(f)
                self.current_term = state["current_term"]
                self.voted_for = state["voted_for"]
                self.log = [LogEntry(**entry) for entry in state["log"]]
                self.commit_index = state["commit_index"]
                self.last_applied = state["last_applied"]
        except FileNotFoundError:
            pass

    def save_state(self):
        """Save persistent state to disk."""
        state_file = os.path.join(self.data_dir, f"raft_state_{self.node_id}.json")
        state = {
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "log": [vars(entry) for entry in self.log],
            "commit_index": self.commit_index,
            "last_applied": self.last_applied
        }
        with open(state_file, "w") as f:
            json.dump(state, f)

    def append_entry(self, command: dict) -> bool:
        """Append a new entry to the log."""
        if self.state != NodeState.LEADER:
            return False
            
        entry = LogEntry(
            term=self.current_term,
            command=command,
            index=len(self.log)
        )
        self.log.append(entry)
        self.save_state()
        
        # Update next_index for all followers
        for i in range(self.num_servers):
            if i != self.node_id:
                self.next_index[i] = len(self.log)
        
        return True

    def request_vote(self, term: int, candidate_id: int, last_log_index: int, last_log_term: int) -> Tuple[bool, int]:
        """Handle RequestVote RPC."""
        if term < self.current_term:
            return False, self.current_term
            
        if term > self.current_term:
            self.current_term = term
            self.state = NodeState.FOLLOWER
            self.voted_for = None
            self.save_state()
            
        # Check if candidate's log is at least as up-to-date as ours
        if (self.voted_for is None or self.voted_for == candidate_id) and \
           (last_log_term > self.log[-1].term if self.log else True or
            last_log_term == self.log[-1].term and last_log_index >= len(self.log) - 1):
            self.voted_for = candidate_id
            self.last_heartbeat = time.time()
            self.save_state()
            return True, self.current_term
            
        return False, self.current_term

    def append_entries(self, term: int, leader_id: int, prev_log_index: int, 
                      prev_log_term: int, entries: List[LogEntry], leader_commit: int) -> Tuple[bool, int]:
        """Handle AppendEntries RPC."""
        if term < self.current_term:
            return False, self.current_term
            
        if term > self.current_term:
            self.current_term = term
            self.state = NodeState.FOLLOWER
            self.voted_for = None
            self.save_state()
            
        self.last_heartbeat = time.time()
        
        # Reply false if log doesn't contain an entry at prev_log_index whose term matches prev_log_term
        if prev_log_index >= len(self.log) or \
           (prev_log_index >= 0 and self.log[prev_log_index].term != prev_log_term):
            return False, self.current_term
            
        # Append any new entries not already in the log
        for i, entry in enumerate(entries):
            log_index = prev_log_index + 1 + i
            if log_index < len(self.log):
                if self.log[log_index].term != entry.term:
                    # Truncate conflicting entries and append new ones
                    self.log = self.log[:log_index]
                    self.log.append(entry)
                    self.save_state()
            else:
                self.log.append(entry)
                self.save_state()
                
        # Update commit_index
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            
        return True, self.current_term

    def start_election(self):
        """Start a new election."""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.save_state()
        
        votes_received = 1  # Vote for self
        
        # Request votes from all other servers
        for i in range(self.num_servers):
            if i != self.node_id:
                # In a real implementation, this would be an RPC call
                # For now, we'll just simulate it
                last_log_index = len(self.log) - 1
                last_log_term = self.log[-1].term if self.log else 0
                # Simulate vote response
                if self.request_vote(self.current_term, self.node_id, last_log_index, last_log_term)[0]:
                    votes_received += 1
                    
        # Check if we won the election
        if votes_received > self.num_servers / 2:
            self.become_leader()
        else:
            self.state = NodeState.FOLLOWER
            self.voted_for = None
            self.save_state()

    def become_leader(self):
        """Transition to leader state."""
        self.state = NodeState.LEADER
        self.last_heartbeat = time.time()
        
        # Initialize leader state
        for i in range(self.num_servers):
            if i != self.node_id:
                self.next_index[i] = len(self.log)
                self.match_index[i] = 0

    def check_timeout(self):
        """Check if election timeout has elapsed."""
        if self.state == NodeState.FOLLOWER and \
           time.time() - self.last_heartbeat > self.election_timeout / 1000:
            self.start_election()

    def send_heartbeat(self):
        """Send heartbeat to all followers."""
        if self.state != NodeState.LEADER:
            return
            
        if time.time() - self.last_heartbeat < self.heartbeat_interval / 1000:
            return
            
        self.last_heartbeat = time.time()
        
        # Send AppendEntries RPC to all servers
        for i in range(self.num_servers):
            if i != self.node_id:
                # In a real implementation, this would be an RPC call
                # For now, we'll just simulate it
                prev_log_index = self.next_index[i] - 1
                prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0
                entries = self.log[self.next_index[i]:]
                self.append_entries(self.current_term, self.node_id, prev_log_index,
                                  prev_log_term, entries, self.commit_index)

    def apply_committed_entries(self):
        """Apply committed entries to the state machine."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            # In a real implementation, this would apply the command to the state machine
            # For now, we'll just print it
            print(f"Applying entry {self.last_applied}: {self.log[self.last_applied].command}") 