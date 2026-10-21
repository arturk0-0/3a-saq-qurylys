"""Request-local bulk reads; never cache decisions across requests or transactions."""


def read_many(store, collection, ids):
    ids = list(dict.fromkeys(key for key in ids if key))
    if not ids:
        return {}
    bulk = getattr(store, "get_many", None)
    if bulk is not None:
        return bulk(collection, ids)
    return {key: store.get(collection, key) for key in ids}


class MaterialReads:
    def __init__(self, store):
        self.store = store
        self.rows = {}

    def load(self, collection, ids):
        rows = self.rows.setdefault(collection, {})
        rows.update(read_many(self.store, collection, (key for key in ids if key not in rows)))

    def get(self, collection, key):
        rows = self.rows.setdefault(collection, {})
        if key not in rows:
            rows[key] = self.store.get(collection, key)
        return rows[key]
