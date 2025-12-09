"""
Modelos de datos para el scrapper de Moodle UCC
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class TipoRecurso(Enum):
    """Tipos de recursos que se pueden encontrar en Moodle"""
    PDF = "pdf"
    POWERPOINT = "powerpoint"
    WORD = "word"
    VIDEO_YOUTUBE = "youtube"
    GOOGLE_DRIVE = "google_drive"
    LINK = "link"
    ARCHIVO = "file"
    CARPETA = "folder"
    DESCONOCIDO = "unknown"


@dataclass
class Recurso:
    """Representa un recurso/elemento dentro de un módulo"""
    nombre: str
    url: str
    tipo: TipoRecurso
    modulo_nombre: str
    materia_nombre: str

    def to_dict(self):
        return {
            "nombre": self.nombre,
            "url": self.url,
            "tipo": self.tipo.value,
            "modulo": self.modulo_nombre,
            "materia": self.materia_nombre
        }


@dataclass
class Modulo:
    """Representa un módulo/unidad dentro de una materia"""
    nombre: str
    url: Optional[str] = None
    recursos: List[Recurso] = field(default_factory=list)

    def agregar_recurso(self, recurso: Recurso):
        self.recursos.append(recurso)


@dataclass
class Materia:
    """Representa una materia/curso en Moodle"""
    nombre: str
    url: str
    id_curso: Optional[str] = None
    modulos: List[Modulo] = field(default_factory=list)

    def agregar_modulo(self, modulo: Modulo):
        self.modulos.append(modulo)

    def total_recursos(self) -> int:
        return sum(len(modulo.recursos) for modulo in self.modulos)
