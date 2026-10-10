"""FinanzAR Desktop — backend local.

El backend corre como sidecar en ``127.0.0.1`` y nunca expone datos financieros
a la red. SQLite es la fuente de verdad estructurada; ChromaDB es la memoria
semántica de recuperación.
"""

__version__ = "0.2.1"
LOCAL_USER_ID = "local"
API_PREFIX = "/api"
