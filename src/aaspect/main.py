def hello(name: str = "world") -> str:
    return f"Hello, {name}!"


def main() -> None:
    print(hello())
