from dataclasses import dataclass

@dataclass
class LogEntry:
    term: int
    command: str
    data: bytes 