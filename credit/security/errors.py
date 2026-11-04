"""Messages métier utiles sans l’écho des instantanés financiers de Pydantic."""

from pydantic import ValidationError


def public_error(exc):
    if isinstance(exc, ValidationError):
        return {
            "code": "invalid_business_data",
            "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],
            "message": "Vérifier types, unités, périodes et états des champs indiqués",
        }
    return str(exc)
