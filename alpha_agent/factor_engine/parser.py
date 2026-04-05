"""Recursive descent parser for the factor expression DSL.

Grammar (operator precedence low → high):
    expr     := compare
    compare  := add_sub ((">" | "<" | ">=" | "<=") add_sub)?
    add_sub  := term (("+"|"-") term)*
    term     := unary (("*"|"/") unary)*
    unary    := "-" unary | power
    power    := atom ("**" atom)?
    atom     := NUMBER | feature | call | "(" expr ")"
    feature  := "$" IDENT
    call     := IDENT "(" arglist ")"
    arglist  := expr ("," expr)*

Examples:
    Rank(-Delta($close, 5))
    ($close - Mean($close, 20)) / Std($close, 20)
    Rank($close / Ref($close, 5) - 1)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from alpha_agent.factor_engine.ast_nodes import (
    BinaryOpNode,
    CallNode,
    ExprNode,
    FeatureNode,
    LiteralNode,
    UnaryOpNode,
)


class TokenType(Enum):
    NUMBER = auto()
    IDENT = auto()
    DOLLAR = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    POWER = auto()
    GT = auto()
    LT = auto()
    GTE = auto()
    LTE = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    pos: int


class ParseError(Exception):
    """Raised when the parser encounters invalid syntax."""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(f"Parse error at position {pos}: {message}")
        self.pos = pos


class Tokenizer:
    """Converts an expression string into a stream of tokens."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self._pos < len(self._text):
            ch = self._text[self._pos]

            if ch.isspace():
                self._pos += 1
                continue

            if ch.isdigit() or (ch == "." and self._peek_digit()):
                tokens.append(self._read_number())
                continue

            if ch.isalpha() or ch == "_":
                tokens.append(self._read_ident())
                continue

            token = self._read_symbol()
            tokens.append(token)

        tokens.append(Token(TokenType.EOF, "", self._pos))
        return tokens

    def _peek_digit(self) -> bool:
        next_pos = self._pos + 1
        return next_pos < len(self._text) and self._text[next_pos].isdigit()

    def _read_number(self) -> Token:
        start = self._pos
        has_dot = False
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isdigit():
                self._pos += 1
            elif ch == "." and not has_dot:
                has_dot = True
                self._pos += 1
            else:
                break
        return Token(TokenType.NUMBER, self._text[start : self._pos], start)

    def _read_ident(self) -> Token:
        start = self._pos
        while self._pos < len(self._text) and (
            self._text[self._pos].isalnum() or self._text[self._pos] == "_"
        ):
            self._pos += 1
        return Token(TokenType.IDENT, self._text[start : self._pos], start)

    def _read_symbol(self) -> Token:
        start = self._pos
        ch = self._text[self._pos]
        self._pos += 1

        two_char_ops = {">=": TokenType.GTE, "<=": TokenType.LTE, "**": TokenType.POWER}
        if self._pos < len(self._text):
            two = ch + self._text[self._pos]
            if two in two_char_ops:
                self._pos += 1
                return Token(two_char_ops[two], two, start)

        single_ops = {
            "$": TokenType.DOLLAR,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            ",": TokenType.COMMA,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "/": TokenType.SLASH,
            ">": TokenType.GT,
            "<": TokenType.LT,
        }
        if ch in single_ops:
            return Token(single_ops[ch], ch, start)

        raise ParseError(f"Unexpected character: {ch!r}", start)


class ExprParser:
    """Parses a factor expression string into an AST.

    Usage:
        parser = ExprParser()
        ast = parser.parse("Rank(-Delta($close, 5))")
    """

    def parse(self, text: str) -> ExprNode:
        tokens = Tokenizer(text).tokenize()
        self._tokens = tokens
        self._pos = 0
        result = self._parse_expr()
        if self._current().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token: {self._current().value!r}", self._current().pos
            )
        return result

    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        token = self._current()
        if token.type != token_type:
            raise ParseError(
                f"Expected {token_type.name}, got {token.type.name} ({token.value!r})",
                token.pos,
            )
        return self._advance()

    def _parse_expr(self) -> ExprNode:
        return self._parse_compare()

    def _parse_compare(self) -> ExprNode:
        left = self._parse_add_sub()
        compare_ops = {TokenType.GT, TokenType.LT, TokenType.GTE, TokenType.LTE}
        if self._current().type in compare_ops:
            op_token = self._advance()
            right = self._parse_add_sub()
            return BinaryOpNode(op=op_token.value, left=left, right=right)
        return left

    def _parse_add_sub(self) -> ExprNode:
        left = self._parse_term()
        while self._current().type in {TokenType.PLUS, TokenType.MINUS}:
            op_token = self._advance()
            right = self._parse_term()
            left = BinaryOpNode(op=op_token.value, left=left, right=right)
        return left

    def _parse_term(self) -> ExprNode:
        left = self._parse_unary()
        while self._current().type in {TokenType.STAR, TokenType.SLASH}:
            op_token = self._advance()
            right = self._parse_unary()
            left = BinaryOpNode(op=op_token.value, left=left, right=right)
        return left

    def _parse_unary(self) -> ExprNode:
        if self._current().type == TokenType.MINUS:
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="-", operand=operand)
        return self._parse_power()

    def _parse_power(self) -> ExprNode:
        base = self._parse_atom()
        if self._current().type == TokenType.POWER:
            self._advance()
            exponent = self._parse_atom()
            return BinaryOpNode(op="**", left=base, right=exponent)
        return base

    def _parse_atom(self) -> ExprNode:
        token = self._current()

        if token.type == TokenType.NUMBER:
            self._advance()
            return LiteralNode(value=float(token.value))

        if token.type == TokenType.DOLLAR:
            self._advance()
            name_token = self._expect(TokenType.IDENT)
            return FeatureNode(name=name_token.value)

        if token.type == TokenType.IDENT:
            return self._parse_call()

        if token.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return expr

        raise ParseError(f"Unexpected token: {token.value!r}", token.pos)

    def _parse_call(self) -> CallNode:
        name_token = self._expect(TokenType.IDENT)
        self._expect(TokenType.LPAREN)

        args: list[ExprNode] = []
        if self._current().type == TokenType.RPAREN:
            raise ParseError(
                f"Function {name_token.value}() requires at least one argument",
                self._current().pos,
            )
        args.append(self._parse_expr())
        while self._current().type == TokenType.COMMA:
            self._advance()
            args.append(self._parse_expr())

        self._expect(TokenType.RPAREN)
        return CallNode(func_name=name_token.value, args=tuple(args))
