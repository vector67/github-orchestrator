def is_thread_key(key: str | int) -> bool:
    text = str(key)
    return bool(text) and text.strip(".") != ""
