"""Fake auto-decisioner: scores an application, calls @guard, approves or denies."""

from custos import guard


@guard()
def decide_loan(application: dict) -> str:
    raise NotImplementedError


if __name__ == "__main__":
    decide_loan({})

