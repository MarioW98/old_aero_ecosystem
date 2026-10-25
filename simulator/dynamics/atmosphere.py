"""
simulator/dynamics/atmosphere.py

Modello atmosferico ISA (International Standard Atmosphere).

D1.2: Fondamenta — atmosfera ISA.

Fornisce temperatura, pressione, densità e velocità del suono in
funzione della quota geopotenziale.

Struttura ISA implementata:
- Troposfera (0 - 11.000 m): T decresce linearmente (lapse rate 0.0065 K/m)
- Stratosfera inferiore (11.000 - 20.000 m): T costante (216.65 K)
- Oltre 20.000 m: estensione della stratosfera inferiore (T costante)

Tutte le unità sono SI:
- quota: metri [m]
- temperatura: Kelvin [K]
- pressione: Pascal [Pa]
- densità: kg/m³
- velocità del suono: m/s
"""

from __future__ import annotations

import math


class Atmosphere:
    """
    Modello ISA (International Standard Atmosphere).

    Uso:
        T   = Atmosphere.temperature(1000.0)      # K
        P   = Atmosphere.pressure(1000.0)         # Pa
        rho = Atmosphere.density(1000.0)          # kg/m³
        a   = Atmosphere.speed_of_sound(1000.0)   # m/s
        q   = Atmosphere.dynamic_pressure(h, V)   # Pa
    """

    # ------------------------------------------------------------------
    # Costanti ISA
    # ------------------------------------------------------------------
    T0 = 288.15           # K, temperatura al livello del mare
    P0 = 101325.0         # Pa, pressione al livello del mare
    RHO0 = 1.225          # kg/m³, densità al livello del mare
    LAPSE_RATE = 0.0065   # K/m, gradiente termico troposfera
    G = 9.80665           # m/s², accelerazione di gravità standard
    R = 287.05            # J/(kg·K), costante dei gas per l'aria secca
    GAMMA = 1.4           # rapporto dei calori specifici (cp/cv)

    # Limiti degli strati atmosferici
    H_TROPOPAUSE = 11000.0    # m, fine troposfera
    H_STRATOSPHERE = 20000.0  # m, fine stratosfera inferiore

    # Esponente per le formule della troposfera: n = g / (L·R) ≈ 5.2559
    _N = G / (LAPSE_RATE * R)

    # Valori alla tropopausa (precalcolati dalle formule della troposfera)
    T_TROPOPAUSE = T0 - LAPSE_RATE * H_TROPOPAUSE          # 216.65 K
    P_TROPOPAUSE = P0 * (T_TROPOPAUSE / T0) ** _N          # ≈ 22632 Pa
    RHO_TROPOPAUSE = RHO0 * (T_TROPOPAUSE / T0) ** (_N - 1.0)  # ≈ 0.364 kg/m³

    # ------------------------------------------------------------------
    # Temperatura
    # ------------------------------------------------------------------
    @classmethod
    def temperature(cls, altitude: float) -> float:
        """
        Temperatura [K] alla quota geopotenziale data.
        Troposfera: decresce linearmente. Stratosfera: costante.
        """
        if altitude <= cls.H_TROPOPAUSE:
            return cls.T0 - cls.LAPSE_RATE * altitude
        else:
            return cls.T_TROPOPAUSE

    # ------------------------------------------------------------------
    # Pressione
    # ------------------------------------------------------------------
    @classmethod
    def pressure(cls, altitude: float) -> float:
        """Pressione [Pa] alla quota geopotenziale data."""
        if altitude <= cls.H_TROPOPAUSE:
            T = cls.T0 - cls.LAPSE_RATE * altitude
            return cls.P0 * (T / cls.T0) ** cls._N
        else:
            # Stratosfera: decadimento esponenziale a T costante
            return cls.P_TROPOPAUSE * math.exp(
                -cls.G * (altitude - cls.H_TROPOPAUSE)
                / (cls.R * cls.T_TROPOPAUSE)
            )

    # ------------------------------------------------------------------
    # Densità
    # ------------------------------------------------------------------
    @classmethod
    def density(cls, altitude: float) -> float:
        """Densità [kg/m³] alla quota geopotenziale data."""
        if altitude <= cls.H_TROPOPAUSE:
            T = cls.T0 - cls.LAPSE_RATE * altitude
            return cls.RHO0 * (T / cls.T0) ** (cls._N - 1.0)
        else:
            return cls.RHO_TROPOPAUSE * math.exp(
                -cls.G * (altitude - cls.H_TROPOPAUSE)
                / (cls.R * cls.T_TROPOPAUSE)
            )

    # ------------------------------------------------------------------
    # Velocità del suono
    # ------------------------------------------------------------------
    @classmethod
    def speed_of_sound(cls, altitude: float) -> float:
        """
        Velocità del suono [m/s] alla quota data.
        a = sqrt(γ · R · T)
        """
        T = cls.temperature(altitude)
        return math.sqrt(cls.GAMMA * cls.R * T)

    # ------------------------------------------------------------------
    # Pressione dinamica
    # ------------------------------------------------------------------
    @classmethod
    def dynamic_pressure(cls, altitude: float, velocity: float) -> float:
        """
        Pressione dinamica q = ½·ρ·V² [Pa].

        Fondamentale per le forze aerodinamiche:
            F = q · S · C
        dove S è l'area di riferimento e C il coefficiente.
        """
        rho = cls.density(altitude)
        return 0.5 * rho * velocity ** 2