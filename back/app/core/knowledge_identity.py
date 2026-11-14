from hashlib import md5


def document_key(source_url: str, revision: str) -> str:
    return md5(f"{source_url}\x1f{revision}".encode(), usedforsecurity=False).hexdigest()


def passage_key(document_stable_id: str, section: str) -> str:
    return md5(f"{document_stable_id}\x1f{section}".encode(), usedforsecurity=False).hexdigest()
