"""Controlled vocabularies for categorical sales fields."""

from enum import Enum


class Region(Enum):
    NORTH_AMERICA = "North America"
    EUROPE = "Europe"
    ASIA_PACIFIC = "Asia Pacific"


class Channel(Enum):
    ONLINE = "Online"
    RETAIL = "Retail"
    DISTRIBUTOR = "Distributor"


class ProductCategory(Enum):
    ELECTRONICS = "Electronics"
    STATIONERY = "Stationery"
    FURNITURE = "Furniture"
