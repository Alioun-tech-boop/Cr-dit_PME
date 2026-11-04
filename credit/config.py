import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://credit:credit_local@localhost:5432/credit"
)
ENGINE_VERSION = "deterministic-0.3.0"
ENGINE_CONFIGURATION = {
    "currency": "XOF",
    "money_decimals": 2,
    "rounding": "ROUND_HALF_UP",
    "combination_policy": "70-30-v1",
    "validated_grid": None,
    "model": None,
}
