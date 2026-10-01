"""
Mixin para los modelos cuyos datos pertenecen a UNA tienda (multi-tienda,
ver app/stores.py): cierres, cuentas, recompras, empleadas, notas/tareas.

- `store_code` se llena solo al insertar con la tienda del request en curso
  (o la tienda por defecto fuera de un request), así un endpoint de creación
  no puede "olvidarse" de asignarla.
- Las lecturas deben pasar por `for_current_store()` /
  `get_for_current_store_or_404()` para no mezclar ni exponer datos de otra
  tienda (incluido editar/borrar por id un registro ajeno).
"""
from flask import abort

from app.models.user import db
from app.stores import DEFAULT_STORE, get_current_store


class StoreScopedMixin:
    store_code = db.Column(
        db.String(20),
        nullable=False,
        default=get_current_store,
        server_default=DEFAULT_STORE,
        index=True,
    )

    @classmethod
    def for_store(cls, store_code):
        return cls.query.filter(cls.store_code == store_code)

    @classmethod
    def for_current_store(cls):
        return cls.for_store(get_current_store())

    @classmethod
    def get_for_current_store_or_404(cls, item_id):
        item = cls.for_current_store().filter(cls.id == item_id).first()
        if item is None:
            abort(404)
        return item
