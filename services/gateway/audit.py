"""Build audit record, hash chain it, enqueue to audit writer."""


def build_record(decision, context) -> dict:
    raise NotImplementedError


def append_to_chain(record: dict) -> str:
    raise NotImplementedError

