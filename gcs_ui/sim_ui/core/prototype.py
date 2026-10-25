from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentPrototype:
    """Descrizione statica di uno strumento disponibile nell'Hangar."""
    type_id: str
    display_name: str
    category: str
    width: float
    height: float
    color: str
    description: str = ""
    style: str = "Base"


class InstrumentRegistry:
    """Catalogo centrale degli strumenti."""

    def __init__(self) -> None:
        self._prototypes: dict[str, InstrumentPrototype] = {}
        self._category_order: list[str] = []

    def register(self, p: InstrumentPrototype) -> None:
        if p.type_id in self._prototypes:
            raise ValueError(f"Già registrato: {p.type_id}")
        self._prototypes[p.type_id] = p
        if p.category not in self._category_order:
            self._category_order.append(p.category)

    def get(self, type_id: str) -> InstrumentPrototype | None:
        return self._prototypes.get(type_id)

    def categories(self) -> tuple[str, ...]:
        return tuple(self._category_order)

    def prototypes_in_category(self, category: str) -> list[InstrumentPrototype]:
        return sorted(
            (p for p in self._prototypes.values() if p.category == category),
            key=lambda p: p.display_name,
        )

    def all_prototypes(self) -> list[InstrumentPrototype]:
        return list(self._prototypes.values())


def build_default_registry() -> InstrumentRegistry:
    r = InstrumentRegistry()




    # --- Volo ---
    r.register(InstrumentPrototype("flight-airspeed", "Airspeed", "Volo",
                                   200, 200, "#2E7D32", "Anemometro", style="Base"))
    r.register(InstrumentPrototype("flight-airspeed-pro", "Airspeed Pro", "Volo",
                                   200, 200, "#1B5E20", "Anemometro Pro", style="Professional"))
    r.register(InstrumentPrototype("flight-altimeter", "Altimeter", "Volo",
                                   200, 200, "#1E88E5", "Altimetro", style="Base"))
    r.register(InstrumentPrototype("flight-altimeter-pro", "Altimeter Pro", "Volo",
                                   200, 200, "#0D47A1", "Altimetro (Professional)", style="Professional"))
    r.register(InstrumentPrototype("flight-attitude", "Attitude", "Volo",
                                   220, 220, "#5E35B1", "Orizzonte Artificiale",style="Base"))
    r.register(InstrumentPrototype("flight-attitude-full", "Attitude Full", "Volo",
                                   240, 240, "#4527A0", "Orizzonte artificiale completo", style="Base"))
    r.register(InstrumentPrototype("flight-attitude-square", "Attitude Square", "Volo",
                                   240, 240, "#311B92", "Orizzonte artificiale quadrato",style="Base"))
    r.register(InstrumentPrototype("flight-vsi-pro", "VSI Pro", "Volo",
                                   200, 200, "#1A237E", "Variometro (Professional)",style="Professional"))
    r.register(InstrumentPrototype("flight-turn-coord", "Turn Coordinator", "Volo",
                                   200, 200, "#6A1B9A", "Virosbandometro",style="Base"))
    r.register(InstrumentPrototype("flight-turn-coord-pro", "Turn Coord Pro", "Volo",
                                   200, 200, "#4A148C", "Virosbandometro (Professional)",style="Professional"))
    ## --- Digital ---
    r.register(InstrumentPrototype("flight-altimeter-digital", "Altimeter Digital", "Volo",
                                   70, 150, "#1E88E5", "Altimetro digitale",style="Digital"))
    r.register(InstrumentPrototype("flight-vsi-digital", "VSI Digital", "Volo",
                                   70, 150, "#283593", "Variometro digitale",style="Digital"))

    # --- Motore ---
    r.register(InstrumentPrototype("engine-rpm", "RPM", "Motore",
                                   200, 200, "#E53935", "Giri motore", style="Base"))
    r.register(InstrumentPrototype("engine-oil-temp", "Oil Temp", "Motore",
                                   180, 180, "#FB8C00", "Temperatura olio", style="Base"))

    # --- Navigazione ---
    r.register(InstrumentPrototype("nav-heading", "Heading", "Navigazione",
                                   200, 200, "#00897B", "Indicatore di prua", style="Base"))
    r.register(InstrumentPrototype("nav-heading-pro", "Heading Pro", "Navigazione",
                                   200, 200, "#004D40", "Indicatore di prua (Professional)", style="Professional"))


    # --- Avanzati (serie speciale) ---
    r.register(InstrumentPrototype("adv-sq-attitude", "Attitude AdvanceSq", "Avanzati",
                                   240, 240, "#00695C",
                                   "Orizzonte artificiale avanzato",style="Advance"))
    r.register(InstrumentPrototype("adv-pfd", "Primary Flight Display", "Avanzati",
                                   960, 720, "#143C8C",
                                   "PFD stile Gulfstream G500/G600", style="Advance"))
    r.register(InstrumentPrototype("pfd-test", "pfd_test_windows", "Avanzati",
                               960, 720, "#143C8C",
                               "PFD test", style="Advance"))
    
    # --- Comfort (anti-affaticamento visivo) ---
    r.register(InstrumentPrototype("comfort-airspeed", "Airspeed Comfort", "Comfort",
                                   200, 200, "#FF7E00",
                                   "Anemometro analogico Comfort",style="Comfort"))
    r.register(InstrumentPrototype("comfort-altimeter", "Altimeter Comfort", "Comfort",
                                   200, 200, "#FF7E00",
                                   "Altimetro analogico Comfort",style="Comfort"))
    r.register(InstrumentPrototype("comfort-vsi", "VSI Comfort", "Comfort",
                                   200, 200, "#FF7E00",
                                   "Variometro analogico Comfort",style="Comfort"))
    r.register(InstrumentPrototype("comfort-heading", "Heading Comfort", "Comfort",
                                   200, 200, "#FF7E00",
                                   "Indicatore di prua Comfort",style="Comfort"))
    r.register(InstrumentPrototype("comfort-turn-coord", "Turn Coord Comfort", "Comfort",
                                   200, 200, "#FF7E00",
                                   "Virosbandometro Comfort",style="Comfort"))
    # --- Display ---
    r.register(InstrumentPrototype("display-viewport", "Simulator Viewport", "Display",
                                   1000, 600, "#2C3E50", "Finestra visuale simulatore",
                                   style="Display"))
    # Mappa 2D di navigazione
    r.register(InstrumentPrototype("display-map", "Map View 2D", "Display",
                                   600, 600, "#1A237E",
                                   "Mappa di navigazione 2D (north-up, aircraft-centered)",
                                   style="Display"))
    # --- Strumenti per Display ---
    r.register(InstrumentPrototype("view-airspeed-tape", "Airspeed Tape", "Visualizzazione",
                                   80, 240, "#1A237E", "Anemometro a nastro verticale",
                                   style="View"))
    r.register(InstrumentPrototype("view-altimeter-tape", "Altimeter Tape", "Visualizzazione",
                                   80, 240, "#1A237E", "Altimetro a nastro verticale",
                                   style="View"))
    r.register(InstrumentPrototype("view-heading-tape", "Heading Tape", "Visualizzazione",
                                   250, 60, "#1A237E", "Bussola a nastro orizzontale",
                                   style="View"))
    return r