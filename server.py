"""
Faker MCP Server
================
A minimal FastMCP server exposing FakerAPI.it endpoints as typed MCP tools.
Designed to be hosted in VS Code as a GitHub Copilot MCP server.

Resources covered:
  • get_persons    - Fetch fake person profiles
  • get_companies  - Fetch fake company records
  • get_products   - Fetch fake product listings
  • get_books      - Fetch fake book records
  • get_addresses  - Fetch fake address records

All tools share three optional parameters:
  quantity  - number of records (1-1000, default 5)
  locale    - BCP-47 locale string  (default "en_US")
  seed      - integer seed for reproducible results
"""

from __future__ import annotations

import httpx
from typing import Annotated, Any
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# ── Base URL ──────────────────────────────────────────────────────────────────
FAKER_BASE = "https://fakerapi.it/api/v2"

# ── Shared parameter type aliases ─────────────────────────────────────────────
Quantity = Annotated[
    int,
    Field(default=5, ge=1, le=1000, description="Number of records to return (1-1000)."),
]
Locale = Annotated[
    str,
    Field(default="en_US", description='BCP-47 locale, e.g. "en_US", "fr_FR", "de_DE".'),
]
Seed = Annotated[
    int | None,
    Field(default=None, description="Optional integer seed for reproducible results."),
]

# ── Response models ───────────────────────────────────────────────────────────

class FakerResponse(BaseModel):
    """Generic wrapper returned by every FakerAPI endpoint."""
    status: str
    code: int
    total: int
    data: list[dict[str, Any]]


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _fetch(resource: str, quantity: int, locale: str, seed: int | None, **extra) -> FakerResponse:
    """Call a FakerAPI.it endpoint and return a typed FakerResponse."""
    params: dict[str, Any] = {
        "_quantity": quantity,
        "_locale": locale,
    }
    if seed is not None:
        params["_seed"] = seed
    params.update(extra)

    # async with httpx.AsyncClient(timeout=10) as client:
    resp = httpx.get(f"{FAKER_BASE}/{resource}", params=params)  # type: ignore[attr-defined]
    # satisfy linters; httpx.AsyncClient.get is a coroutine  # noqa: E501
    resp.raise_for_status()
    return FakerResponse.model_validate(resp.json())


# ── MCP server ────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="faker-api",
    instructions=(
        "Use these tools to fetch realistic fake data for testing and prototyping. "
        "All tools call https://fakerapi.it under the hood."
    ),
)


# ── Tool: persons ─────────────────────────────────────────────────────────────

class PersonsResult(BaseModel):
    """Result of get_persons."""
    total: int = Field(description="Total records returned.")
    persons: list[dict[str, Any]] = Field(description="List of fake person objects.")


@mcp.tool(description="Fetch fake person profiles (id, firstname, lastname, email, phone, birthday, gender, address, website, image).")
def get_persons(
    quantity: Quantity = 5,
    locale: Locale = "en_US",
    seed: Seed = None,
    gender: Annotated[
        str | None,
        Field(default=None, description='Filter by gender: "male", "female", or "other".'),
    ] = None,
) -> PersonsResult:
    extra = {}
    if gender:
        extra["_gender"] = gender
    resp =  _fetch("persons", quantity, locale, seed, **extra)
    return PersonsResult(total=resp.total, persons=resp.data)


# ── Tool: companies ───────────────────────────────────────────────────────────

class CompaniesResult(BaseModel):
    """Result of get_companies."""
    total: int = Field(description="Total records returned.")
    companies: list[dict[str, Any]] = Field(description="List of fake company objects.")


@mcp.tool(description="Fetch fake company records (id, name, email, vat, phone, country, addresses, website, image, contact).")
def get_companies(
    quantity: Quantity = 5,
    locale: Locale = "en_US",
    seed: Seed = None,
) -> CompaniesResult:
    resp = _fetch("companies", quantity, locale, seed)
    return CompaniesResult(total=resp.total, companies=resp.data)


# ── Tool: products ────────────────────────────────────────────────────────────

class ProductsResult(BaseModel):
    """Result of get_products."""
    total: int = Field(description="Total records returned.")
    products: list[dict[str, Any]] = Field(description="List of fake product objects.")


@mcp.tool(description="Fetch fake product listings (id, name, description, ean, upc, image, net_price, taxes, price, categories, tags).")
def get_products(
    quantity: Quantity = 5,
    locale: Locale = "en_US",
    seed: Seed = None,
    categories_number: Annotated[
        int,
        Field(default=2, ge=1, le=5, description="Number of product categories per item (1-5)."),
    ] = 2,
) -> ProductsResult:
    resp = _fetch("products", quantity, locale, seed, _categories_number=categories_number)
    return ProductsResult(total=resp.total, products=resp.data)


# ── Tool: books ───────────────────────────────────────────────────────────────

class BooksResult(BaseModel):
    """Result of get_books."""
    total: int = Field(description="Total records returned.")
    books: list[dict[str, Any]] = Field(description="List of fake book objects.")


@mcp.tool(description="Fetch fake book records (id, title, author, genre, description, isbn, image, published, publisher).")
def get_books(
    quantity: Quantity = 5,
    locale: Locale = "en_US",
    seed: Seed = None,
) -> BooksResult:
    resp = _fetch("books", quantity, locale, seed)
    return BooksResult(total=resp.total, books=resp.data)


# ── Tool: addresses ───────────────────────────────────────────────────────────

class AddressesResult(BaseModel):
    """Result of get_addresses."""
    total: int = Field(description="Total records returned.")
    addresses: list[dict[str, Any]] = Field(description="List of fake address objects.")


@mcp.tool(description="Fetch fake address records (id, street, streetName, buildingNumber, city, zipcode, country, country_code, latitude, longitude).")
def get_addresses(
    quantity: Quantity = 5,
    locale: Locale = "en_US",
    seed: Seed = None,
    country_code: Annotated[
        str | None,
        Field(default=None, description='ISO 3166-1 alpha-2 country code to force, e.g. "US", "DE", "FR".'),
    ] = None,
) -> AddressesResult:
    extra = {}
    if country_code:
        extra["country_code"] = country_code
    resp = _fetch("addresses", quantity, locale, seed, **extra)
    return AddressesResult(total=resp.total, addresses=resp.data)



# code-mode
from code_mode import execute_code as _execute_code

@mcp.tool(description=(
    "Write and execute Python code that orchestrates faker tools. "
    "Use this instead of calling tools one by one. "
    "Available functions: get_persons(), get_companies(), get_products(), get_books(), get_addresses(). "
    "Each accepts quantity, locale, seed. "
    "Must define def run(): or async def run(): and return the result."
))
def execute_code(code: Annotated[str, Field(description="Python code with a run() function.")]) -> dict:
    return _execute_code(code)
# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    
    mcp.run(transport="stdio")