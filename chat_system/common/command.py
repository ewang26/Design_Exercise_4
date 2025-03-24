import pickle
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

class CommandType(Enum):
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LOGOUT = 3
    LIST_USERS = 4
    DELETE_ACCOUNT = 5
    SEND_MESSAGE = 6
    POP_UNREAD_MESSAGES = 7
    DELETE_MESSAGES = 8
    GET_UNREAD_COUNT = 9
    GET_READ_MESSAGES = 10

@dataclass
class Command:
    command_type: CommandType
    data: Dict[str, Any]
    client_id: Optional[str] = None  # For tracking which client sent the command
    
    def serialize(self) -> bytes:
        """Serialize the command to bytes for storage/transmission"""
        return pickle.dumps(self)
    
    @staticmethod
    def deserialize(data: bytes) -> 'Command':
        """Deserialize a command from bytes"""
        return pickle.loads(data)
    
    def __str__(self) -> str:
        return f"Command({self.command_type.name}, {self.data})"

def create_command(command_type: CommandType, **kwargs) -> Command:
    """Helper function to create commands with proper data structure"""
    return Command(command_type=command_type, data=kwargs) 