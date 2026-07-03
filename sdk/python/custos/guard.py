"""@guard decorator and `with custos.gate(...)` context manager."""

from contextlib import contextmanager


def guard(*args, **kwargs):
    def decorator(fn):
        return fn

    return decorator


@contextmanager
def gate(*args, **kwargs):
    yield

