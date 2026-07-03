"""API-key middleware -> tenant resolution."""


async def resolve_tenant(api_key: str) -> str:
    raise NotImplementedError

