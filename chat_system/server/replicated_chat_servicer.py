import pickle
import grpc
import threading
import time
import queue
from typing import List, Dict, Any, Optional

from ..proto import chat_pb2, chat_pb2_grpc
from ..common.user import Message

class ReplicatedChatServicer(chat_pb2_grpc.ChatServiceServicer):
    """Chat service implementation that uses Raft for replication."""
    
    def __init__(self, raft_node):
        self.raft_node = raft_node
        # Map of client connections to usernames
        self.client_sessions = {}
        self.sessions_lock = threading.RLock()
    
    def CreateAccount(self, request, context):
        """Create a new user account."""
        username = request.username
        password = request.password
        
        # Check if username already exists in local state (fast path)
        with self.raft_node.state_lock:
            if username in self.raft_node.server_state['users']:
                return chat_pb2.CreateAccountResponse(error="Username already exists")
        
        # Command must go through leader
        command_data = pickle.dumps((username, password))
        success, error = self.raft_node.append_command('create_account', command_data)
        
        if not success:
            return chat_pb2.CreateAccountResponse(error=error)
        
        # Wait for command to be applied (could add timeout)
        max_retries = 10
        for _ in range(max_retries):
            with self.raft_node.state_lock:
                if username in self.raft_node.server_state['users']:
                    return chat_pb2.CreateAccountResponse()
            time.sleep(0.1)
        
        return chat_pb2.CreateAccountResponse(error="Command timed out")
    
    def Login(self, request, context):
        """Log in to an existing account."""
        username = request.username
        password = request.password
        
        with self.raft_node.state_lock:
            if username not in self.raft_node.server_state['users']:
                return chat_pb2.LoginResponse(error="Username does not exist")
            
            stored_password = self.raft_node.server_state['users'][username]['password']
            if password != stored_password:  # In a real system, use password hashing
                return chat_pb2.LoginResponse(error="Incorrect password")
        
        # Store session information
        with self.sessions_lock:
            peer = context.peer()
            self.client_sessions[peer] = username
        
        return chat_pb2.LoginResponse()
    
    def Logout(self, request, context):
        """Log out of the current session."""
        with self.sessions_lock:
            peer = context.peer()
            if peer in self.client_sessions:
                self.client_sessions[peer] = None
        
        return chat_pb2.LogoutResponse()
    
    def DeleteAccount(self, request, context):
        """Delete the current user's account."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        # Command must go through leader
        command_data = pickle.dumps(username)
        success, error = self.raft_node.append_command('delete_account', command_data)
        
        if not success:
            context.abort(grpc.StatusCode.UNAVAILABLE, error)
        
        # Clear session
        with self.sessions_lock:
            self.client_sessions[peer] = None
        
        return chat_pb2.DeleteAccountResponse()
    
    def ListUsers(self, request, context):
        """List users matching a pattern."""
        pattern = request.pattern
        offset = request.offset
        limit = request.limit
        
        with self.raft_node.state_lock:
            all_users = list(self.raft_node.server_state['users'].keys())
            
            # Filter by pattern if provided
            if pattern:
                import re
                regex = re.compile(pattern.replace("*", ".*"))
                matching_users = [user for user in all_users if regex.match(user)]
            else:
                matching_users = all_users
            
            # Sort for consistent results
            matching_users.sort()
            
            # Apply pagination
            start = offset
            end = offset + limit if limit > 0 else len(matching_users)
            result_users = matching_users[start:end]
        
        return chat_pb2.ListUsersResponse(usernames=result_users)
    
    def SendMessage(self, request, context):
        """Send a message to another user."""
        # Verify sender is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            sender = self.client_sessions[peer]
        
        recipient = request.receiver
        content = request.content
        
        # Verify recipient exists
        with self.raft_node.state_lock:
            if recipient not in self.raft_node.server_state['users']:
                context.abort(grpc.StatusCode.NOT_FOUND, "Recipient not found")
        
        # Command must go through leader
        command_data = pickle.dumps((sender, recipient, content))
        success, error = self.raft_node.append_command('send_message', command_data)
        
        if not success:
            context.abort(grpc.StatusCode.UNAVAILABLE, error)
        
        # Notify if recipient is online (this would be more complex in a real distributed system)
        self._notify_user_if_online(recipient)
        
        return chat_pb2.SendMessageResponse()
    
    def GetNumberOfUnreadMessages(self, request, context):
        """Get the number of unread messages for the current user."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        with self.raft_node.state_lock:
            user_data = self.raft_node.server_state['users'].get(username)
            if not user_data:
                context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            
            count = len(user_data['messages']['unread'])
        
        return chat_pb2.GetNumberOfUnreadMessagesResponse(count=count)
    
    def GetNumberOfReadMessages(self, request, context):
        """Get the number of read messages for the current user."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        with self.raft_node.state_lock:
            user_data = self.raft_node.server_state['users'].get(username)
            if not user_data:
                context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            
            count = len(user_data['messages']['read'])
        
        return chat_pb2.GetNumberOfReadMessagesResponse(count=count)
    
    def PopUnreadMessages(self, request, context):
        """Pop unread messages and move them to read messages."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        num_messages = request.num_messages
        
        # Get the unread message ids first
        with self.raft_node.state_lock:
            user_data = self.raft_node.server_state['users'].get(username)
            if not user_data:
                context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            
            unread_ids = user_data['messages']['unread'][:num_messages] if num_messages > 0 else user_data['messages']['unread']
            messages = []
            
            # Convert to message objects
            for msg_id in unread_ids:
                if msg_id in self.raft_node.server_state['messages']:
                    msg = self.raft_node.server_state['messages'][msg_id]
                    pb_msg = chat_pb2.Message(
                        id=msg['id'],
                        sender=msg['sender'],
                        content=msg['content']
                    )
                    messages.append(pb_msg)
        
        # Execute the move operation through Raft
        # First mark as read
        for msg_id in unread_ids:
            command_data = pickle.dumps((username, 'mark_read', msg_id))
            success, error = self.raft_node.append_command('message_operation', command_data)
            if not success:
                context.abort(grpc.StatusCode.UNAVAILABLE, error)
        
        return chat_pb2.PopUnreadMessagesResponse(messages=messages)
    
    def GetReadMessages(self, request, context):
        """Get read messages for the current user."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        offset = request.offset
        num_messages = request.num_messages
        
        with self.raft_node.state_lock:
            user_data = self.raft_node.server_state['users'].get(username)
            if not user_data:
                context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            
            read_ids = user_data['messages']['read']
            
            # Apply pagination
            start = offset
            end = offset + num_messages if num_messages > 0 else len(read_ids)
            
            result_ids = read_ids[start:end]
            messages = []
            
            # Convert to message objects
            for msg_id in result_ids:
                if msg_id in self.raft_node.server_state['messages']:
                    msg = self.raft_node.server_state['messages'][msg_id]
                    pb_msg = chat_pb2.Message(
                        id=msg['id'],
                        sender=msg['sender'],
                        content=msg['content']
                    )
                    messages.append(pb_msg)
        
        return chat_pb2.GetReadMessagesResponse(messages=messages)
    
    def DeleteMessages(self, request, context):
        """Delete messages for the current user."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        message_ids = request.message_ids
        
        # Command must go through leader
        command_data = pickle.dumps((username, message_ids))
        success, error = self.raft_node.append_command('delete_messages', command_data)
        
        if not success:
            context.abort(grpc.StatusCode.UNAVAILABLE, error)
        
        return chat_pb2.DeleteMessagesResponse()
    
    def SubscribeToMessages(self, request, context):
        """Subscribe to new message notifications."""
        # Verify user is logged in
        with self.sessions_lock:
            peer = context.peer()
            if peer not in self.client_sessions or not self.client_sessions[peer]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")
            username = self.client_sessions[peer]
        
        # Create a queue for this subscription
        message_queue = queue.Queue()
        
        # Register the subscription
        with self.raft_node.state_lock:
            if 'subscribers' not in self.raft_node.server_state:
                self.raft_node.server_state['subscribers'] = {}
            
            if username not in self.raft_node.server_state['subscribers']:
                self.raft_node.server_state['subscribers'][username] = []
            
            self.raft_node.server_state['subscribers'][username].append(message_queue)
        
        try:
            # Keep listening for new messages
            while context.is_active():
                try:
                    message = message_queue.get(timeout=1.0)
                    pb_msg = chat_pb2.Message(
                        id=message['id'],
                        sender=message['sender'],
                        content=message['content']
                    )
                    yield chat_pb2.MessageNotification(message=pb_msg)
                except queue.Empty:
                    continue
        finally:
            # Clean up subscription when client disconnects
            with self.raft_node.state_lock:
                if username in self.raft_node.server_state.get('subscribers', {}):
                    if message_queue in self.raft_node.server_state['subscribers'][username]:
                        self.raft_node.server_state['subscribers'][username].remove(message_queue)
    
    def _notify_user_if_online(self, username):
        """Helper to notify a user of new messages if they're online."""
        # This would be more complex in a real distributed system
        with self.raft_node.state_lock:
            if 'subscribers' in self.raft_node.server_state and username in self.raft_node.server_state['subscribers']:
                # Get the latest message for this user
                user_data = self.raft_node.server_state['users'].get(username)
                if user_data and user_data['messages']['unread']:
                    latest_msg_id = user_data['messages']['unread'][-1]
                    if latest_msg_id in self.raft_node.server_state['messages']:
                        message = self.raft_node.server_state['messages'][latest_msg_id]
                        
                        # Notify all subscribers for this user
                        for sub_queue in self.raft_node.server_state['subscribers'][username]:
                            try:
                                sub_queue.put(message)
                            except:
                                pass  # Handle potential errors in notification 