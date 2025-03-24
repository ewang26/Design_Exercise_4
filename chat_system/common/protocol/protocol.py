from dataclasses import dataclass
from enum import IntEnum
from typing import List, Dict, Type, Tuple

from ..user import Message


class MessageType(IntEnum):
    # Account operations
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LOGOUT = 3
    LIST_USERS = 4
    DELETE_ACCOUNT = 5

    # Message operations
    SEND_MESSAGE = 6
    RECEIVED_MESSAGE = 7
    GET_NUMBER_OF_UNREAD_MESSAGES = 8
    GET_NUMBER_OF_READ_MESSAGES = 9
    POP_UNREAD_MESSAGES = 10
    GET_READ_MESSAGES = 11
    DELETE_MESSAGES = 12


class ProtocolMessage:
    type: MessageType

    def pack_server(self) -> bytes:
        """ Packs the message to be sent to the server. """
        pass

    def pack_client(self, data: any) -> bytes:
        """ Packs the message to be sent to the client. """
        pass

    @classmethod
    def unpack_server(cls, data: bytes) -> Tuple[any, int]:
        """ Unpacks the message sent to the server. Returns both the result and the number of bytes consumed. """
        pass

    @classmethod
    def unpack_client(cls, data: bytes) -> Tuple[any, int]:
        """ Unpacks the message sent to the client. Returns both the result and the number of bytes consumed. """
        pass


@dataclass
class CreateAccountMessage(ProtocolMessage):
    type = MessageType.CREATE_ACCOUNT
    name: str
    password: str


@dataclass
class LoginMessage(ProtocolMessage):
    type = MessageType.LOGIN
    name: str
    password: str

@dataclass
class LogoutMessage(ProtocolMessage):
    type = MessageType.LOGOUT
    pass

@dataclass
class ListUsersMessage(ProtocolMessage):
    type = MessageType.LIST_USERS
    pattern: str
    offset: int
    limit: int

@dataclass
class DeleteAccountMessage(ProtocolMessage):
    type = MessageType.DELETE_ACCOUNT
    pass


@dataclass
class SendMessageMessage(ProtocolMessage):
    type = MessageType.SEND_MESSAGE
    receiver: str
    content: str


@dataclass
class ReceivedMessageMessage(ProtocolMessage):
    type = MessageType.RECEIVED_MESSAGE
    new_message: Message


@dataclass
class GetNumberOfUnreadMessagesMessage(ProtocolMessage):
    type = MessageType.GET_NUMBER_OF_UNREAD_MESSAGES
    pass

@dataclass
class GetNumberOfReadMessagesMessage(ProtocolMessage):
    type = MessageType.GET_NUMBER_OF_READ_MESSAGES
    pass


@dataclass
class PopUnreadMessagesMessage(ProtocolMessage):
    type = MessageType.POP_UNREAD_MESSAGES
    num_messages: int


@dataclass
class GetReadMessagesMessage(ProtocolMessage):
    type = MessageType.GET_READ_MESSAGES
    offset: int
    num_messages: int


@dataclass
class DeleteMessagesMessage(ProtocolMessage):
    type = MessageType.DELETE_MESSAGES
    message_ids: List[int]


class Protocol:
    message_classes: Dict[MessageType, Type[ProtocolMessage]]

    def get_message_type(self, data: bytes) -> MessageType:
        pass

    def message_class(self, msg_type: MessageType) -> Type[ProtocolMessage]:
        return self.message_classes[msg_type]
