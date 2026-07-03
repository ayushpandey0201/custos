"""Maps verdict -> execute / raise Blocked / route review."""


class Blocked(Exception):
    pass


def enforce(verdict: dict):
    raise NotImplementedError

