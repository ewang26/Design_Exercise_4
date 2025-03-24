"""
This file prints out the sizes of the protocol messages for each of the protocol types:
- Custom protocol
- JSON protocol
- gRPC protocol
"""

import unittest

from chat_system.common.protocol.custom_protocol import *
from chat_system.common.protocol.json_protocol import *
from chat_system.proto import chat_pb2


def print_protocol_sizes(type, custom_bytes, json_bytes, grpc_msg):
    print(type)
    print(f"\tCustom: {len(custom_bytes)}")
    print(f"\tJSON: {len(json_bytes)}")
    print(f"\tgRPC: {len(grpc_msg.SerializeToString())}")

class TestProtocolSizes(unittest.TestCase):
    def test_create_account(self):
        """Test creating account message size."""
        username = "testuser"
        password = "testpass"

        custom = Custom_CreateAccountMessage(username, password)
        json = JSON_CreateAccountMessage(username, password)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.CreateAccountRequest(username=username, password=password)

        print_protocol_sizes("CreateAccountRequest", custom_req, json_req, grpc_req)

        # Responses, no error
        custom_req = custom.pack_client(None)
        json_req = json.pack_client(None)
        grpc_req = chat_pb2.CreateAccountResponse(error=None)

        print_protocol_sizes("CreateAccountResponse, no error", custom_req, json_req, grpc_req)

        # Responses, with error
        custom_req = custom.pack_client("Username taken")
        json_req = json.pack_client("Username taken")
        grpc_req = chat_pb2.CreateAccountResponse(error="Username taken")

        print_protocol_sizes("CreateAccountResponse, with error", custom_req, json_req, grpc_req)

    def test_login(self):
        """Test login message size."""
        username = "testuser"
        password = "testpass"

        custom = Custom_LoginMessage(username, password)
        json = JSON_LoginMessage(username, password)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.LoginRequest(username=username, password=password)

        print_protocol_sizes("LoginRequest", custom_req, json_req, grpc_req)

        # Responses, no error
        custom_req = custom.pack_client(None)
        json_req = json.pack_client(None)
        grpc_req = chat_pb2.LoginResponse()

        print_protocol_sizes("LoginResponse, no error", custom_req, json_req, grpc_req)

        # Responses, with error
        custom_req = custom.pack_client("Invalid username or password")
        json_req = json.pack_client("Invalid username or password")
        grpc_req = chat_pb2.LoginResponse(error="Invalid username or password")

        print_protocol_sizes("LoginResponse, with error", custom_req, json_req, grpc_req)

    def test_logout(self):
        """Test logout message size."""
        custom = Custom_LogoutMessage()
        json = JSON_LogoutMessage()

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.LogoutRequest()

        print_protocol_sizes("LogoutRequest", custom_req, json_req, grpc_req)


    def test_delete_account(self):
        """Test delete account message size."""
        custom = Custom_DeleteAccountMessage()
        json = JSON_DeleteAccountMessage()

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.DeleteAccountRequest()

        print_protocol_sizes("DeleteAccountRequest", custom_req, json_req, grpc_req)

    def test_list_users(self):
        """Test list users message size."""
        pattern = "test*"
        offset = 0
        limit = 10

        custom = Custom_ListUsersMessage(pattern, offset, limit)
        json = JSON_ListUsersMessage(pattern, offset, limit)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.ListUsersRequest(pattern=pattern, offset=offset, limit=limit)

        print_protocol_sizes("ListUsersRequest", custom_req, json_req, grpc_req)

        # Responses
        usernames = ["testuser1", "testuser2"]
        custom_req = custom.pack_client([User(name, [], []) for name in usernames])
        json_req = json.pack_client([User(name, [], []) for name in usernames])
        grpc_req = chat_pb2.ListUsersResponse(usernames=usernames)

        print_protocol_sizes("ListUsersResponse", custom_req, json_req, grpc_req)

    def test_send_message(self):
        """Test send message message size."""
        sender = "testuser1"
        receiver = "testuser2"
        content = "Hello!"

        custom = Custom_SendMessageMessage(receiver, content)
        json = JSON_SendMessageMessage(receiver, content)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.SendMessageRequest(receiver=receiver, content=content)

        print_protocol_sizes("SendMessageRequest", custom_req, json_req, grpc_req)

    def test_get_number_of_unread_messages(self):
        """Test get number of unread messages message size."""
        count = 10

        custom = Custom_GetNumberOfUnreadMessagesMessage()
        json = JSON_GetNumberOfUnreadMessagesMessage()

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.GetNumberOfUnreadMessagesRequest()

        print_protocol_sizes("GetNumberOfUnreadMessagesRequest", custom_req, json_req, grpc_req)

        # Responses
        custom_req = custom.pack_client(count)
        json_req = json.pack_client(count)
        grpc_req = chat_pb2.GetNumberOfUnreadMessagesResponse(count=count)

        print_protocol_sizes("GetNumberOfUnreadMessagesResponse", custom_req, json_req, grpc_req)

    def test_get_number_of_read_messages(self):
        """Test get number of read messages message size."""
        count = 10

        custom = Custom_GetNumberOfReadMessagesMessage()
        json = JSON_GetNumberOfReadMessagesMessage()

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.GetNumberOfReadMessagesRequest()

        print_protocol_sizes("GetNumberOfReadMessagesRequest", custom_req, json_req, grpc_req)

        # Responses
        custom_req = custom.pack_client(count)
        json_req = json.pack_client(count)
        grpc_req = chat_pb2.GetNumberOfReadMessagesResponse(count=count)

        print_protocol_sizes("GetNumberOfReadMessagesResponse", custom_req, json_req, grpc_req)

    def test_pop_unread_messages(self):
        """Test pop unread messages message size."""
        count = 10

        custom = Custom_PopUnreadMessagesMessage(count)
        json = JSON_PopUnreadMessagesMessage(count)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.PopUnreadMessagesRequest(num_messages=count)

        print_protocol_sizes("PopUnreadMessagesRequest", custom_req, json_req, grpc_req)

        # Responses
        messages = [Message(1, "testuser1", "Hello!"), Message(2, "testuser2", "Hello!")]
        custom_req = custom.pack_client(messages)
        json_req = json.pack_client(messages)
        grpc_req = chat_pb2.PopUnreadMessagesResponse(messages=[
            chat_pb2.Message(id=1, sender="testuser1", content="Hello!"),
            chat_pb2.Message(id=2, sender="testuser2", content="Hello!")
        ])

        print_protocol_sizes("PopUnreadMessagesResponse", custom_req, json_req, grpc_req)

    def test_get_read_messages(self):
        """Test get read messages message size."""
        offset = 0
        limit = 10

        custom = Custom_GetReadMessagesMessage(offset, limit)
        json = JSON_GetReadMessagesMessage(offset, limit)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.GetReadMessagesRequest(offset=offset, num_messages=limit)

        print_protocol_sizes("GetReadMessagesRequest", custom_req, json_req, grpc_req)

        # Responses
        messages = [Message(1, "testuser1", "Hello!"), Message(2, "testuser2", "Hello!")]
        custom_req = custom.pack_client(messages)
        json_req = json.pack_client(messages)
        grpc_req = chat_pb2.GetReadMessagesResponse(messages=[
            chat_pb2.Message(id=1, sender="testuser1", content="Hello!"),
            chat_pb2.Message(id=2, sender="testuser2", content="Hello!")
        ])

        print_protocol_sizes("GetReadMessagesResponse", custom_req, json_req, grpc_req)

    def test_delete_messages(self):
        """Test delete messages message size."""
        message_ids = [1, 2]

        custom = Custom_DeleteMessagesMessage(message_ids)
        json = JSON_DeleteMessagesMessage(message_ids)

        # Requests
        custom_req = custom.pack_server()
        json_req = json.pack_server()
        grpc_req = chat_pb2.DeleteMessagesRequest(message_ids=message_ids)

        print_protocol_sizes("DeleteMessagesRequest", custom_req, json_req, grpc_req)

    def test_received_message_notification(self):
        """Test received message notification message size."""
        message = Message(1, "testuser1", "Hello!")
        custom = Custom_ReceivedMessageMessage(message)
        json = JSON_ReceivedMessageMessage(message)

        # Notifications
        custom_req = custom.pack_client(None)
        json_req = json.pack_client(None)
        grpc_req = chat_pb2.MessageNotification(
            message=chat_pb2.Message(id=1, sender="testuser1", content="Hello!")
        )

        print_protocol_sizes("MessageNotification", custom_req, json_req, grpc_req)
