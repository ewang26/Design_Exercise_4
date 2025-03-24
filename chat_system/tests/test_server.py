import unittest
import grpc

from chat_system.common.config import ConnectionSettings
from chat_system.server.server import ChatServer, ChatServicer
from chat_system.proto import chat_pb2


class MockContext:
    def __init__(self):
        self.peer_value = "test_peer"

    def peer(self):
        return self.peer_value

    def abort(self, code, message):
        raise grpc.RpcError(f"Error {code}: {message}")

    def is_active(self):
        return True

class TestServer(unittest.TestCase):
    def setUp(self):
        """Create a new server instance for each test."""
        self.server = ChatServer(ConnectionSettings())
        self.servicer = ChatServicer(self.server)
        self.context = MockContext()

    def test_create_account(self):
        """Test account creation."""
        request = chat_pb2.CreateAccountRequest(
            username="test",
            password="password"
        )
        response = self.servicer.CreateAccount(request, self.context)
        self.assertFalse(response.HasField('error'))

        # Test duplicate account
        response = self.servicer.CreateAccount(request, self.context)
        self.assertTrue(response.HasField('error'))

        # Test empty username
        empty_request = chat_pb2.CreateAccountRequest(
            username="",
            password="password"
        )
        response = self.servicer.CreateAccount(empty_request, self.context)
        self.assertTrue(response.HasField('error'))

    def test_login_logout(self):
        """Test login and logout functionality."""
        # Create account first
        create_request = chat_pb2.CreateAccountRequest(
            username="test",
            password="password"
        )
        self.servicer.CreateAccount(create_request, self.context)

        # Test successful login
        login_request = chat_pb2.LoginRequest(
            username="test",
            password="password"
        )
        response = self.servicer.Login(login_request, self.context)
        self.assertFalse(response.HasField('error'))
        self.assertEqual(self.server.client_sessions[self.context.peer()], "test")

        # Test wrong password
        wrong_password_request = chat_pb2.LoginRequest(
            username="test",
            password="wrong_password"
        )
        response = self.servicer.Login(wrong_password_request, self.context)
        self.assertTrue(response.HasField('error'))

        # Test non-existent user
        nonexistent_request = chat_pb2.LoginRequest(
            username="nonexistent",
            password="password"
        )
        response = self.servicer.Login(nonexistent_request, self.context)
        self.assertTrue(response.HasField('error'))

        # Test logout
        logout_request = chat_pb2.LogoutRequest()
        self.servicer.Logout(logout_request, self.context)
        self.assertIsNone(self.server.client_sessions[self.context.peer()])

    def test_list_users(self):
        """Test listing users."""
        # Create multiple accounts
        usernames = ["alice", "bob", "charlie", "dave"]
        for username in usernames:
            request = chat_pb2.CreateAccountRequest(
                username=username,
                password="password"
            )
            self.servicer.CreateAccount(request, self.context)

        # Test listing all users
        list_request = chat_pb2.ListUsersRequest(
            pattern="*",
            offset=0,
            limit=-1
        )
        response = self.servicer.ListUsers(list_request, self.context)
        self.assertEqual(len(response.usernames), len(usernames))
        for username in usernames:
            self.assertIn(username, response.usernames)

        # Test pattern matching
        pattern_request = chat_pb2.ListUsersRequest(
            pattern="a*",  # Should match alice
            offset=0,
            limit=-1
        )
        response = self.servicer.ListUsers(pattern_request, self.context)
        self.assertEqual(len(response.usernames), 1)
        self.assertIn("alice", response.usernames)

        # Test pagination
        paginated_request = chat_pb2.ListUsersRequest(
            pattern="*",
            offset=1,
            limit=2
        )
        response = self.servicer.ListUsers(paginated_request, self.context)
        self.assertEqual(len(response.usernames), 2)

    def test_send_message(self):
        """Test sending messages between users."""
        # Create two accounts
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="sender", password="password"),
            self.context
        )
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="receiver", password="password"),
            self.context
        )

        # Login as sender
        self.servicer.Login(
            chat_pb2.LoginRequest(username="sender", password="password"),
            self.context
        )

        # Send message
        send_request = chat_pb2.SendMessageRequest(
            receiver="receiver",
            content="Hello, receiver!"
        )
        self.servicer.SendMessage(send_request, self.context)

        # Check that receiver has an unread message
        # Create a new context for the receiver
        receiver_context = MockContext()
        receiver_context.peer_value = "receiver_peer"

        # Login as receiver
        self.servicer.Login(
            chat_pb2.LoginRequest(username="receiver", password="password"),
            receiver_context
        )

        # Check unread message count
        unread_request = chat_pb2.GetNumberOfUnreadMessagesRequest()
        unread_response = self.servicer.GetNumberOfUnreadMessages(unread_request, receiver_context)
        self.assertEqual(unread_response.count, 1)

        # Pop the unread message
        pop_request = chat_pb2.PopUnreadMessagesRequest(num_messages=1)
        pop_response = self.servicer.PopUnreadMessages(pop_request, receiver_context)
        self.assertEqual(len(pop_response.messages), 1)
        self.assertEqual(pop_response.messages[0].sender, "sender")
        self.assertEqual(pop_response.messages[0].content, "Hello, receiver!")

        # Check that the message is now in read messages
        read_count_request = chat_pb2.GetNumberOfReadMessagesRequest()
        read_count_response = self.servicer.GetNumberOfReadMessages(read_count_request, receiver_context)
        self.assertEqual(read_count_response.count, 1)

        # Get the read message
        read_request = chat_pb2.GetReadMessagesRequest(offset=0, num_messages=1)
        read_response = self.servicer.GetReadMessages(read_request, receiver_context)
        self.assertEqual(len(read_response.messages), 1)
        self.assertEqual(read_response.messages[0].sender, "sender")
        self.assertEqual(read_response.messages[0].content, "Hello, receiver!")

    def test_subscribe_messages(self):
        """Test that a user can subscribe to messages."""
        # Create two accounts
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="sender", password="password"),
            self.context
        )
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="receiver", password="password"),
            self.context
        )

        # Login as sender
        self.servicer.Login(
            chat_pb2.LoginRequest(username="sender", password="password"),
            self.context
        )

        # Login as receiver
        receiver_context = MockContext()
        receiver_context.peer_value = "receiver_peer"

        # Login as receiver
        self.servicer.Login(
            chat_pb2.LoginRequest(username="receiver", password="password"),
            receiver_context
        )

        # Subscribe to messages
        subscribe_request = chat_pb2.SubscribeRequest()
        message_stream = self.servicer.SubscribeToMessages(subscribe_request, receiver_context)

        # Send message
        send_request = chat_pb2.SendMessageRequest(
            receiver="receiver",
            content="Hello, receiver!"
        )
        self.servicer.SendMessage(send_request, self.context)

        # Check that receiver has message in the stream
        message = next(message_stream).message
        self.assertEqual(message.sender, "sender")
        self.assertEqual(message.content, "Hello, receiver!")

        # Check unread message count
        unread_request = chat_pb2.GetNumberOfUnreadMessagesRequest()
        unread_response = self.servicer.GetNumberOfUnreadMessages(unread_request, receiver_context)
        self.assertEqual(unread_response.count, 0)

        # Check that the message is now in read messages
        read_count_request = chat_pb2.GetNumberOfReadMessagesRequest()
        read_count_response = self.servicer.GetNumberOfReadMessages(read_count_request, receiver_context)
        self.assertEqual(read_count_response.count, 1)

        # Get the read message
        read_request = chat_pb2.GetReadMessagesRequest(offset=0, num_messages=1)
        read_response = self.servicer.GetReadMessages(read_request, receiver_context)
        self.assertEqual(len(read_response.messages), 1)
        self.assertEqual(read_response.messages[0].sender, "sender")
        self.assertEqual(read_response.messages[0].content, "Hello, receiver!")

    def test_delete_messages(self):
        """Test deleting messages."""
        # Create accounts and send messages
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="sender", password="password"),
            self.context
        )
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="receiver", password="password"),
            self.context
        )

        # Login as sender
        self.servicer.Login(
            chat_pb2.LoginRequest(username="sender", password="password"),
            self.context
        )

        # Send multiple messages
        for i in range(3):
            send_request = chat_pb2.SendMessageRequest(
                receiver="receiver",
                content=f"Message {i}"
            )
            self.servicer.SendMessage(send_request, self.context)

        # Login as receiver
        receiver_context = MockContext()
        receiver_context.peer_value = "receiver_peer"
        self.servicer.Login(
            chat_pb2.LoginRequest(username="receiver", password="password"),
            receiver_context
        )

        # Pop all messages to read mailbox
        pop_request = chat_pb2.PopUnreadMessagesRequest(num_messages=-1)
        pop_response = self.servicer.PopUnreadMessages(pop_request, receiver_context)
        self.assertEqual(len(pop_response.messages), 3)

        # Delete the second message
        message_id = pop_response.messages[1].id
        delete_request = chat_pb2.DeleteMessagesRequest(message_ids=[message_id])
        self.servicer.DeleteMessages(delete_request, receiver_context)

        # Check that only 2 messages remain
        read_count_request = chat_pb2.GetNumberOfReadMessagesRequest()
        read_count_response = self.servicer.GetNumberOfReadMessages(read_count_request, receiver_context)
        self.assertEqual(read_count_response.count, 2)

        # Get the remaining messages and verify the deleted one is gone
        read_request = chat_pb2.GetReadMessagesRequest(offset=0, num_messages=-1)
        read_response = self.servicer.GetReadMessages(read_request, receiver_context)
        self.assertEqual(len(read_response.messages), 2)
        message_ids = [msg.id for msg in read_response.messages]
        self.assertNotIn(message_id, message_ids)

    def test_delete_account(self):
        """Test account deletion."""
        # Create an account
        self.servicer.CreateAccount(
            chat_pb2.CreateAccountRequest(username="test_user", password="password"),
            self.context
        )

        # Login
        self.servicer.Login(
            chat_pb2.LoginRequest(username="test_user", password="password"),
            self.context
        )

        # Delete the account
        delete_request = chat_pb2.DeleteAccountRequest()
        self.servicer.DeleteAccount(delete_request, self.context)

        # Verify the account is deleted by trying to login again
        login_request = chat_pb2.LoginRequest(
            username="test_user",
            password="password"
        )
        response = self.servicer.Login(login_request, self.context)
        self.assertTrue(response.HasField('error'))
