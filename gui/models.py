from dataclasses import dataclass


@dataclass(frozen=True)
class Materia:
    """Representación mínima de una materia usada por la UI."""

    nombre: str
    url: str
    id_curso: str

    @classmethod
    def from_core(cls, value: dict) -> "Materia":
        return cls(
            nombre=str(value.get("name", "")).strip(),
            url=str(value.get("url", "")).strip(),
            id_curso=str(value.get("id", "")).strip(),
        )

    def to_core(self, mode: dict) -> dict:
        return {
            "id": int(self.id_curso),
            "name": self.nombre,
            "url": self.url,
            "mode": mode.get("mode", "update"),
            "scan_existing": bool(mode.get("scan_existing", True)),
        }

