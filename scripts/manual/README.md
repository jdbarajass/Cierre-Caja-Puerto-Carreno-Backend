# Scripts de prueba manual

Llaman a un servidor **real** (local o desplegado) con un usuario real. No son tests de pytest (por eso no viven en `tests/` ni se llaman `test_*.py`).

```bash
# Con el backend corriendo (por defecto http://localhost:5000)
python scripts/manual/check_analytics_endpoints.py
python scripts/manual/check_size_analysis.py
python scripts/manual/check_product_sizes_simple.py
```

Credenciales: variables `KOAJ_API_URL`, `KOAJ_TEST_EMAIL`, `KOAJ_TEST_PASSWORD`; si faltan, se piden por consola. **Nunca** escribirlas en el código.
