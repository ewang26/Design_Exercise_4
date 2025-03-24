import unittest
from chat_system.common.protocol.custom_protocol import (
    CustomProtocol,
    Custom_CreateAccountMessage, Custom_LoginMessage,
    Custom_ListUsersMessage
)
from chat_system.common.user import User

class TestCustomProtocol(unittest.TestCase):
    def setUp(self):
        self.protocol = CustomProtocol()

    def test_create_account(self):
        """Test creating account message."""
        username = "testuser"
        password = "testpass"

        # Create and pack message
        message = Custom_CreateAccountMessage(username, password)
        packed = message.pack_server()

        # Unpack and verify
        unpacked, _ = Custom_CreateAccountMessage.unpack_server(packed)
        self.assertEqual(unpacked.name, username)
        self.assertEqual(unpacked.password, password)

        # Test error response
        error_msg = "Username taken"
        packed_response = message.pack_client(error_msg)
        unpacked_response, _ = Custom_CreateAccountMessage.unpack_client(packed_response)
        self.assertEqual(unpacked_response, error_msg)

    def test_login(self):
        """Test login message."""
        username = "testuser"
        password = "testpass"

        # Create and pack message
        message = Custom_LoginMessage(username, password)
        packed = message.pack_server()

        # Unpack and verify
        unpacked, _ = Custom_LoginMessage.unpack_server(packed)
        self.assertEqual(unpacked.name, username)
        self.assertEqual(unpacked.password, password)

    def test_list_users(self):
        """Test list users message."""
        pattern = "test*"
        offset = 0
        limit = 10

        # Create and pack message
        message = Custom_ListUsersMessage(pattern, offset, limit)
        packed = message.pack_server()

        # Unpack and verify
        unpacked, _ = Custom_ListUsersMessage.unpack_server(packed)
        self.assertEqual(unpacked.pattern, pattern)
        self.assertEqual(unpacked.offset, offset)
        self.assertEqual(unpacked.limit, limit)

        # Test response with user list
        users = ["user0", "user1", "user2"]
        users_obj = [User(name, [], []) for name in users]
        packed_response = message.pack_client(users_obj)
        unpacked_response, _ = Custom_ListUsersMessage.unpack_client(packed_response)
        self.assertEqual(unpacked_response, users)
