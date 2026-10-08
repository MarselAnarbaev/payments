import os


# Тестовый ключ действует только в процессе pytest и не заменяет ключ развёртывания.
os.environ.setdefault("API_KEY", "test-only-api-key")
