import struct
from typing import Optional, Tuple, Self
from .protocol import *
from ..user import Message, User

def encode_str(s: str) -> bytes:
    """Encode a string into bytes with length prefix."""
    b = s.encode('utf-8')
    return struct.pack('!L', len(b)) + b

def decode_str(data: bytes, offset: int = 0) -> Tuple[str, int]:
    """Decode a string from bytes with length prefix."""
    length = struct.unpack('!L', data[offset:offset+4])[0]
    s = data[offset+4:offset+4+length].decode('utf-8')
    return s, offset + 4 + length

def encode_int(i: int) -> bytes:
    """Encode an integer into bytes."""
    return struct.pack('!L', i)

def decode_int(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode an integer from bytes."""
    i = struct.unpack('!L', data[offset:offset+4])[0]
    return i, offset + 4

def encode_bool(b: bool) -> bytes:
    """Encode a boolean into bytes."""
    return struct.pack('!B', 1 if b else 0)

def decode_bool(data: bytes, offset: int = 0) -> Tuple[bool, int]:
    """Decode a boolean from bytes."""
    b = struct.unpack('!B', data[offset:offset+1])[0]
    return b == 1, offset + 1

def encode_message(msg: Message) -> bytes:
    """Encode a Message object into bytes."""
    return encode_int(msg.id) + encode_str(msg.sender) + encode_str(msg.content)

def decode_message(data: bytes, offset: int = 0) -> Tuple[Message, int]:
    """Decode a Message object from bytes."""
    msg_id, offset = decode_int(data, offset)
    sender, offset = decode_str(data, offset)
    content, offset = decode_str(data, offset)
    return Message(msg_id, sender, content), offset

class Custom_CreateAccountMessage(CreateAccountMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + name + password"""
        return struct.pack('!B', self.type.value) + encode_str(self.name) + encode_str(self.password)

    def pack_client(self, data: Optional[str]) -> bytes:
        """Pack response for client: type + has_error + [error_message]"""
        has_error = data is not None
        result = struct.pack('!B', self.type.value) + encode_bool(has_error)
        if has_error:
            result += encode_str(data)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then name + password"""
        name, offset = decode_str(data, 1)  # Skip message type
        password, offset = decode_str(data, offset)
        return cls(name, password), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[Optional[str], int]:
        """Unpack client response: skip type, then has_error + [error_message]"""
        has_error, offset = decode_bool(data, 1)  # Skip message type
        if has_error:
            error, offset = decode_str(data, offset)
            return error, offset
        return None, offset

class Custom_LoginMessage(LoginMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + name + password"""
        return struct.pack('!B', self.type.value) + encode_str(self.name) + encode_str(self.password)

    def pack_client(self, data: Optional[str]) -> bytes:
        """Pack response for client: type + has_error + [error_message]"""
        has_error = data is not None
        result = struct.pack('!B', self.type.value) + encode_bool(has_error)
        if has_error:
            result += encode_str(data)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then name + password"""
        name, offset = decode_str(data, 1)  # Skip message type
        password, offset = decode_str(data, offset)
        return cls(name, password), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[Optional[str], int]:
        """Unpack client response: skip type, then has_error + [error_message]"""
        has_error, offset = decode_bool(data, 1)  # Skip message type
        if has_error:
            error, offset = decode_str(data, offset)
            return error, offset
        return None, offset

class Custom_LogoutMessage(LogoutMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + name + password"""
        return struct.pack('!B', self.type.value)

    def pack_client(self, data: Optional[str]) -> bytes:
        """Pack response for client: type + has_error + [error_message]"""
        pass

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then name + password"""
        return cls(), 1

    @classmethod
    def unpack_client(cls, data: bytes) -> None:
        """Unpack client response: skip type, then has_error + [error_message]"""
        pass

class Custom_ListUsersMessage(ListUsersMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + pattern + offset + limit"""
        return (struct.pack('!B', self.type.value) +
                encode_str(self.pattern) +
                encode_int(self.offset) +
                encode_int(self.limit))

    def pack_client(self, data: List[User]) -> bytes:
        """Pack response for client: type + count + usernames"""
        result = struct.pack('!B', self.type.value)
        result += encode_int(len(data))
        for user in data:
            result += encode_str(user.name)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then pattern + offset + limit"""
        pattern, offset = decode_str(data, 1)  # Skip message type
        list_offset, offset = decode_int(data, offset)
        limit, offset = decode_int(data, offset)
        return cls(pattern, list_offset, limit), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[List[str], int]:
        """Unpack client response: skip type, then count + usernames"""
        count, offset = decode_int(data, 1)  # Skip message type
        usernames = []
        for _ in range(count):
            username, offset = decode_str(data, offset)
            usernames.append(username)
        return usernames, offset


class Custom_DeleteAccountMessage(DeleteAccountMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type only"""
        return struct.pack('!B', self.type.value)

    def pack_client(self, data: None) -> bytes:
        """Pack response for client: type only"""
        return struct.pack('!B', self.type.value)

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: type only"""
        return cls(), 1

    @classmethod
    def unpack_client(cls, data: bytes) -> None:
        """Unpack client response: type only"""
        return None

class Custom_SendMessageMessage(SendMessageMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + recipient_username + content"""
        return (struct.pack('!B', self.type.value) +
                encode_str(self.receiver) +
                encode_str(self.content))

    def pack_client(self, data: Optional[str]) -> bytes:
        """Pack response for client: type + optional error message"""
        result = struct.pack('!B', self.type.value)
        if data is not None:  # Error message
            result += encode_bool(True) + encode_str(data)
        else:
            result += encode_bool(False)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then recipient_username + content"""
        recipient, pos = decode_str(data, 1)  # Skip message type
        content, offset = decode_str(data, pos)
        return cls(recipient, content), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[Optional[str], int]:
        """Unpack client response: skip type, then optional error message"""
        has_error, offset = decode_bool(data, 1)
        if has_error:
            error_msg, offset = decode_str(data, offset)
            return error_msg, offset
        return None, offset

class Custom_ReceivedMessageMessage(ReceivedMessageMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + message"""
        pass

    def pack_client(self, data: None) -> bytes:
        """Pack response for client: type + message"""
        return struct.pack('!B', self.type.value) + encode_message(self.new_message)

    @classmethod
    def unpack_server(cls, data: bytes) -> Self:
        """Unpack server message: skip type, then message"""
        pass

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack client response: skip type, then message"""
        message, offset = decode_message(data, 1)  # Skip message type
        return cls(message), offset

class Custom_GetNumberOfUnreadMessagesMessage(GetNumberOfUnreadMessagesMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type only"""
        return struct.pack('!B', self.type.value)

    def pack_client(self, data: int) -> bytes:
        """Pack response for client: type + count"""
        return struct.pack('!B', self.type.value) + encode_int(data)

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: type only"""
        return cls(), 1

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[int, int]:
        """Unpack client response: skip type, then count"""
        count, offset = decode_int(data, 1)  # Skip message type
        return count, offset


class Custom_GetNumberOfReadMessagesMessage(GetNumberOfReadMessagesMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type only"""
        return struct.pack('!B', self.type.value)

    def pack_client(self, data: int) -> bytes:
        """Pack response for client: type + count"""
        return struct.pack('!B', self.type.value) + encode_int(data)

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: type only"""
        return cls(), 1

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[int, int]:
        """Unpack client response: skip type, then count"""
        count, offset = decode_int(data, 1)  # Skip message type
        return count, offset

class Custom_PopUnreadMessagesMessage(PopUnreadMessagesMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + num_messages"""
        return struct.pack('!B', self.type.value) + encode_int(self.num_messages)

    def pack_client(self, data: List[Message]) -> bytes:
        """Pack response for client: type + count + messages"""
        result = struct.pack('!B', self.type.value) + encode_int(len(data))
        for message in data:
            result += encode_message(message)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then num_messages"""
        num_messages, offset = decode_int(data, 1)  # Skip message type
        return cls(num_messages), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[List[Message], int]:
        """Unpack client response: skip type, then count + messages"""
        count, offset = decode_int(data, 1)  # Skip message type
        messages = []
        for _ in range(count):
            message, offset = decode_message(data, offset)
            messages.append(message)
        return messages, offset

class Custom_GetReadMessagesMessage(GetReadMessagesMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + offset + num_messages"""
        return (struct.pack('!B', self.type.value) +
                encode_int(self.offset) +
                encode_int(self.num_messages))

    def pack_client(self, data: List[Message]) -> bytes:
        """Pack response for client: type + count + messages"""
        result = struct.pack('!B', self.type.value) + encode_int(len(data))
        for message in data:
            result += encode_message(message)
        return result

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then offset + num_messages"""
        offset, next_offset = decode_int(data, 1)  # Skip message type
        num_messages, next_offset = decode_int(data, next_offset)
        return cls(offset, num_messages), next_offset

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[List[Message], int]:
        """Unpack client response: skip type, then count + messages"""
        count, offset = decode_int(data, 1)  # Skip message type
        messages = []
        for _ in range(count):
            message, offset = decode_message(data, offset)
            messages.append(message)
        return messages, offset

class Custom_DeleteMessagesMessage(DeleteMessagesMessage):
    def pack_server(self) -> bytes:
        """Pack message for server: type + count + message_ids"""
        result = struct.pack('!B', self.type.value) + encode_int(len(self.message_ids))
        for msg_id in self.message_ids:
            result += encode_int(msg_id)
        return result

    def pack_client(self, data: None) -> bytes:
        """Pack response for client: type only"""
        return struct.pack('!B', self.type.value)

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[Self, int]:
        """Unpack server message: skip type, then count + message_ids"""
        count, offset = decode_int(data, 1)  # Skip message type
        message_ids = []
        for _ in range(count):
            msg_id, offset = decode_int(data, offset)
            message_ids.append(msg_id)
        return cls(message_ids), offset

    @classmethod
    def unpack_client(cls, data: bytes) -> None:
        """Unpack client response: type only"""
        return None

class CustomProtocol(Protocol):
    """Custom binary protocol implementation."""
    message_classes: Dict[MessageType, Type[ProtocolMessage]] = {
        MessageType.CREATE_ACCOUNT: Custom_CreateAccountMessage,
        MessageType.LOGIN: Custom_LoginMessage,
        MessageType.LOGOUT: Custom_LogoutMessage,
        MessageType.LIST_USERS: Custom_ListUsersMessage,
        MessageType.DELETE_ACCOUNT: Custom_DeleteAccountMessage,
        MessageType.SEND_MESSAGE: Custom_SendMessageMessage,
        MessageType.RECEIVED_MESSAGE: Custom_ReceivedMessageMessage,
        MessageType.GET_NUMBER_OF_UNREAD_MESSAGES: Custom_GetNumberOfUnreadMessagesMessage,
        MessageType.GET_NUMBER_OF_READ_MESSAGES: Custom_GetNumberOfReadMessagesMessage,
        MessageType.POP_UNREAD_MESSAGES: Custom_PopUnreadMessagesMessage,
        MessageType.GET_READ_MESSAGES: Custom_GetReadMessagesMessage,
        MessageType.DELETE_MESSAGES: Custom_DeleteMessagesMessage,
    }

    def get_message_type(self, data: bytes) -> MessageType:
        """Extract message type from first byte of message."""
        if not data:
            raise ValueError("Empty message received")
        try:
            return MessageType(data[0])
        except ValueError as e:
            raise ValueError(f"Invalid message type: {data[0]}") from e

    def message_class(self, msg_type: MessageType) -> Type[ProtocolMessage]:
        """Get the message class for a given message type."""
        if msg_type not in self.message_classes:
            raise ValueError(f"Unsupported message type: {msg_type}")
        return self.message_classes[msg_type]
