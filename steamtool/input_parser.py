"""Quoted game names and item correction; errors stay in the CLI, never Feature errors."""
from collections import deque
from dataclasses import dataclass
from enum import Enum
import re


MESSAGES = {
    "QUERY_NAME_NOT_QUOTED": '游戏名称必须使用 ASCII 英文双引号 "..." 包围。',
    "QUERY_INVALID_QUOTE": '请使用 ASCII 英文双引号，不要使用中文或弯引号作为边界。',
    "QUERY_UNCLOSED_QUOTE": '游戏名称的双引号没有闭合。',
    "QUERY_EMPTY_NAME": '游戏名称不能为空。',
    "QUERY_UNEXPECTED_CHAR": '只接受带双引号的游戏名称；项目之间使用英文逗号。',
    "QUERY_INVALID_ESCAPE": '名称内的双引号应写成两个双引号，不能使用反斜杠转义。',
}


@dataclass
class QueryError(Exception):
    code: str
    item_index: int
    raw: str
    column: int

    def __str__(self):
        return f"第 {self.item_index} 项输入错误：{self.raw}\n{self.code}: {MESSAGES[self.code]}"


@dataclass
class ParsedItem:
    index: int
    raw: str
    name: str | None
    error: QueryError | None


def parse_names(line):
    """Recover comma-separated bad fields while honoring commas and doubled quotes in names."""
    result = []
    cursor, size = 0, len(line)
    if not line.strip():
        return result
    while cursor <= size:
        start = cursor
        while cursor < size and line[cursor].isspace():
            cursor += 1
        value, code = None, None
        if cursor == size or line[cursor] == ',':
            code = "QUERY_EMPTY_NAME"
        elif line[cursor] != '"':
            code = "QUERY_INVALID_QUOTE" if line[cursor] in '“”「」『』＂‘’' else "QUERY_NAME_NOT_QUOTED"
            while cursor < size and line[cursor] != ',':
                cursor += 1
        else:
            cursor += 1
            characters = []
            closed = False
            while cursor < size:
                char = line[cursor]
                if char == '\\' and cursor + 1 < size and line[cursor + 1] in '"\\nrt':
                    code = "QUERY_INVALID_ESCAPE"
                    characters.extend(line[cursor:cursor + 2])
                    cursor += 2
                elif char == '"':
                    if cursor + 1 < size and line[cursor + 1] == '"':
                        characters.append('"')
                        cursor += 2
                    else:
                        cursor += 1
                        closed = True
                        break
                else:
                    characters.append(char)
                    cursor += 1
            if not closed:
                code = code or "QUERY_UNCLOSED_QUOTE"
            else:
                value = ''.join(characters).strip()
                while cursor < size and line[cursor].isspace():
                    cursor += 1
                if cursor < size and line[cursor] != ',':
                    code = code or "QUERY_UNEXPECTED_CHAR"
                    while cursor < size and line[cursor] != ',':
                        cursor += 1
                if not value:
                    code = code or "QUERY_EMPTY_NAME"
                elif value.isascii() and value.isdigit() or re.match(r'(?i)^https?://', value):
                    code = code or "QUERY_UNEXPECTED_CHAR"
        raw, index = line[start:cursor].strip(), len(result) + 1
        error = QueryError(code, index, raw, start + 1) if code else None
        result.append(ParsedItem(index, raw, None if error else value, error))
        if cursor >= size:
            break
        cursor += 1  # The delimiter, not any comma inside a quoted name.
    return result


class InputState(str, Enum):
    COLLECTING_INPUT = "COLLECTING_INPUT"
    CORRECTING_ITEM = "CORRECTING_ITEM"


class GamesInput:
    """A correction blank drops just the current item; a collection blank finishes the batch."""
    def __init__(self):
        self.state = InputState.COLLECTING_INPUT
        self.names = []
        self.pending = deque()
        self.done = False

    @property
    def error(self):
        return self.pending[0].error if self.pending else None

    def advance(self):
        while self.pending and self.pending[0].error is None:
            self.names.append(self.pending.popleft().name)
        self.state = InputState.CORRECTING_ITEM if self.pending else InputState.COLLECTING_INPUT

    def feed(self, line):
        if self.done:
            raise ValueError("Input collection already finished")
        if self.state == InputState.COLLECTING_INPUT:
            if not line.strip():
                self.done = True
            else:
                self.pending.extend(parse_names(line))
                self.advance()
        elif not line.strip():
            self.pending.popleft()
            self.advance()
        else:
            original = self.pending[0]
            corrected = parse_names(line)
            if len(corrected) != 1:
                original.error = QueryError("QUERY_UNEXPECTED_CHAR", original.index, line, 1)
            elif corrected[0].error:
                original.error = QueryError(corrected[0].error.code, original.index, corrected[0].raw,
                                            corrected[0].error.column)
            else:
                corrected[0].index = original.index
                self.pending[0] = corrected[0]
                self.advance()
        return self.error
