"""Machine-readable catalog for the three published products."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PRODUCT_CATALOG_PATH = Path(__file__).resolve().parent / "product_catalog.json"


class ProductCatalogError(Exception):
    """Raised when the product catalog is malformed."""


@dataclass(frozen=True)
class ProductDefinition:
    slug: str
    name: str
    summary: str
    license_features: tuple[str, ...]
    modules: tuple[str, ...]
    validators: tuple[str, ...]
    documentation: tuple[str, ...]
    release_artifacts: tuple[str, ...]
    deferred: tuple[str, ...]


def load_product_catalog(path: Path = PRODUCT_CATALOG_PATH) -> tuple[ProductDefinition, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    products = tuple(_product_from_mapping(item) for item in raw["products"])
    slugs = [product.slug for product in products]
    if len(set(slugs)) != len(slugs):
        raise ProductCatalogError("product catalog contains duplicate slugs")
    return products


def product_slugs(path: Path = PRODUCT_CATALOG_PATH) -> tuple[str, ...]:
    return tuple(product.slug for product in load_product_catalog(path))


def product_by_slug(slug: str, path: Path = PRODUCT_CATALOG_PATH) -> ProductDefinition:
    for product in load_product_catalog(path):
        if product.slug == slug:
            return product
    raise ProductCatalogError(f"unknown product slug: {slug}")


def _product_from_mapping(value: dict[str, object]) -> ProductDefinition:
    return ProductDefinition(
        slug=str(value["slug"]),
        name=str(value["name"]),
        summary=str(value["summary"]),
        license_features=tuple(str(item) for item in value["license_features"]),
        modules=tuple(str(item) for item in value["modules"]),
        validators=tuple(str(item) for item in value["validators"]),
        documentation=tuple(str(item) for item in value["documentation"]),
        release_artifacts=tuple(str(item) for item in value["release_artifacts"]),
        deferred=tuple(str(item) for item in value["deferred"]),
    )
