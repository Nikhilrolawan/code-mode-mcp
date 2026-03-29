import subprocess
import textwrap
import json
from typing import Annotated
from pydantic import Field

TOOL_BOOTSTRAP = """
import httpx, json

FAKER_BASE = "https://fakerapi.it/api/v2"

def _fetch(resource, quantity=5, locale="en_US", seed=None, **extra):
    params = {"_quantity": quantity, "_locale": locale}
    if seed:
        params["_seed"] = seed
    params.update(extra)
    r = httpx.get(f"{FAKER_BASE}/{resource}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()["data"]

def get_persons(quantity=5, locale="en_US", seed=None, **kw):
    return _fetch("persons", quantity, locale, seed, **kw)

def get_companies(quantity=5, locale="en_US", seed=None, **kw):
    return _fetch("companies", quantity, locale, seed, **kw)

def get_products(quantity=5, locale="en_US", seed=None, **kw):
    return _fetch("products", quantity, locale, seed, **kw)

def get_books(quantity=5, locale="en_US", seed=None, **kw):
    return _fetch("books", quantity, locale, seed, **kw)

def get_addresses(quantity=5, locale="en_US", seed=None, **kw):
    return _fetch("addresses", quantity, locale, seed, **kw)
"""

def execute_code(code: Annotated[str, Field(description="Python code to execute. Must define a def run(): or async def run():")]) -> dict:
    wrapper = textwrap.dedent(f"""
{TOOL_BOOTSTRAP}
import asyncio

{code}

result = asyncio.run(run()) if asyncio.iscoroutinefunction(run) else run()
print(json.dumps(result, ensure_ascii=False))
""")
    proc = subprocess.run(
        ["python", "-c", wrapper],
        capture_output=True, text=True, timeout=15
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    return {"result": json.loads(proc.stdout)}