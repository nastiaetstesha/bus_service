import os
import json
from pathlib import Path
from typing import Iterator, Dict, Any


def load_routes(directory_path: str = "routes") -> Iterator[Dict[str, Any]]:
    """Итерируемся по *.json в папке и отдаём разобранные маршруты.
    Требуется, чтобы внутри у маршрута был атрибут 'name' и массив 'coordinates'.
    """
    dir_path = Path(directory_path)
    for p in sorted(dir_path.glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            route = json.load(f)
        # лёгкая валидация
        if "name" in route and "coordinates" in route:
            yield route


# usage example
for route in load_routes():
    pass  # do something