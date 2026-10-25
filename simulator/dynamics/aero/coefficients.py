"""
simulator/dynamics/aero/coefficients.py

Tabelle aerodinamiche e interpolazione dei coefficienti.

D2.1: Fondamenta aerodinamiche — coefficienti in funzione di alpha.

Approccio: tabelle di punti (alpha, coefficiente) con interpolazione
lineare. Questo gestisce naturalmente:
- Regione lineare pre-stallo
- Transizione allo stallo
- Post-stallo (comportamento tipo "flat plate")

Il modello è parametrico: ogni velivolo ha la sua configurazione.
Questo permette di riusare la stessa classe per C172, J3 Cub, biplano,
e in futuro il tailsitter (con tabelle estese fino a ±90°).
"""

from __future__ import annotations

import numpy as np


class AeroConfig:
    """
    Configurazione aerodinamica di un velivolo.

    Contiene le tabelle dei coefficienti e i parametri geometrici.
    Le tabelle sono array numpy: alpha [rad] vs coefficiente.
    """

    def __init__(self,
                 alpha_table: np.ndarray,
                 CL_table: np.ndarray,
                 CD_table: np.ndarray,
                 Cm_table: np.ndarray,
                 S_ref: float,
                 b_ref: float,
                 c_ref: float,
                 # Effetti superfici di controllo
                 CL_delta_e: float = 0.0,
                 CD_delta_e: float = 0.02,
                 Cm_delta_e: float = -1.2,
                 Cl_delta_a: float = 0.08,
                 Cn_delta_r: float = 0.06,
                 CY_delta_r: float = 0.15,
                 # Effetti smorzamento rotazionale (adimensionali)
                 Cm_q: float = -12.0,
                 Cl_p: float = -0.4,
                 Cn_r: float = -0.1,
                 CY_p: float = -0.05):
        """
        Args:
            alpha_table: angoli di attacco [rad], crescente.
            CL_table: coefficiente di portanza per ogni alpha.
            CD_table: coefficiente di resistenza per ogni alpha.
            Cm_table: coefficiente di momento di beccheggio per ogni alpha.
            S_ref: area alare di riferimento [m²].
            b_ref: apertura alare [m].
            c_ref: corda media aerodinamica [m].
            CL_delta_e: dCL/d(delta_elevator) [1/rad].
            CD_delta_e: dCD/d(delta_elevator) [1/rad].
            Cm_delta_e: dCm/d(delta_elevator) [1/rad] (negativo = nose-down).
            Cl_delta_a: dCl/d(delta_aileron) [1/rad].
            Cn_delta_r: dCn/d(delta_rudder) [1/rad].
            CY_delta_r: dCY/d(delta_rudder) [1/rad].
            Cm_q: smorzamento di beccheggio [1/rad].
            Cl_p: smorzamento di rollio [1/rad].
            Cn_r: smorzamento di imbardata [1/rad].
            CY_p: forza laterale da roll rate [1/rad].
        """
        self.alpha_table = np.asarray(alpha_table, dtype=float)
        self.CL_table = np.asarray(CL_table, dtype=float)
        self.CD_table = np.asarray(CD_table, dtype=float)
        self.Cm_table = np.asarray(Cm_table, dtype=float)

        # Verifica coerenza dimensioni
        n = len(self.alpha_table)
        assert len(self.CL_table) == n, "CL_table deve avere stessa lunghezza di alpha_table"
        assert len(self.CD_table) == n, "CD_table deve avere stessa lunghezza di alpha_table"
        assert len(self.Cm_table) == n, "Cm_table deve avere stessa lunghezza di alpha_table"

        # Geometria
        self.S_ref = S_ref
        self.b_ref = b_ref
        self.c_ref = c_ref
        self.AR = b_ref ** 2 / S_ref  # Aspect ratio

        # Superfici di controllo
        self.CL_delta_e = CL_delta_e
        self.CD_delta_e = CD_delta_e
        self.Cm_delta_e = Cm_delta_e
        self.Cl_delta_a = Cl_delta_a
        self.Cn_delta_r = Cn_delta_r
        self.CY_delta_r = CY_delta_r

        # Smorzamento rotazionale
        self.Cm_q = Cm_q
        self.Cl_p = Cl_p
        self.Cn_r = Cn_r
        self.CY_p = CY_p


class AeroCoefficients:
    """
    Calcola i coefficienti aerodinamici per interpolazione dalle tabelle.

    Uso:
        config = make_c172_config()
        aero = AeroCoefficients(config)
        CL, CD, Cm, ... = aero.compute(alpha, beta, delta_e, delta_a, delta_r, ...)
    """

    def __init__(self, config: AeroConfig):
        self.config = config

    def compute(self,
                alpha: float,
                beta: float = 0.0,
                delta_e: float = 0.0,
                delta_a: float = 0.0,
                delta_r: float = 0.0,
                p_hat: float = 0.0,
                q_hat: float = 0.0,
                r_hat: float = 0.0) -> dict:
        """
        Calcola tutti i coefficienti aerodinamici.

        Args:
            alpha: angolo di attacco [rad].
            beta: angolo di sideslip [rad].
            delta_e: deflessione elevatore [rad] (positivo = trailing edge down).
            delta_a: deflessione alettoni [rad] (positivo = roll destro).
            delta_r: deflessione timone [rad] (positivo = trailing edge left).
            p_hat: roll rate adimensionale p·b/(2V).
            q_hat: pitch rate adimensionale q·c/(2V).
            r_hat: yaw rate adimensionale r·b/(2V).

        Returns:
            dict con i coefficienti totali:
            'CL', 'CD', 'Cm', 'Cl', 'Cn', 'CY'
        """
        cfg = self.config

        # Interpolazione dalle tabelle
        CL_base = float(np.interp(alpha, cfg.alpha_table, cfg.CL_table))
        CD_base = float(np.interp(alpha, cfg.alpha_table, cfg.CD_table))
        Cm_base = float(np.interp(alpha, cfg.alpha_table, cfg.Cm_table))

        # Contributi delle superfici di controllo
        CL = CL_base + cfg.CL_delta_e * delta_e
        CD = CD_base + cfg.CD_delta_e * abs(delta_e)
        Cm = Cm_base + cfg.Cm_delta_e * delta_e + cfg.Cm_q * q_hat

        # Coefficienti laterali-direzionali
        # Roll da alettoni + smorzamento
        Cl = cfg.Cl_delta_a * delta_a + cfg.Cl_p * p_hat

        # Yaw da timone + smorzamento
        Cn = cfg.Cn_delta_r * delta_r + cfg.Cn_r * r_hat

        # Forza laterale da sideslip + timone + roll rate
        # CY_beta è derivato dalla geometria (approssimazione)
        CY_beta = -0.3  # tipico per aereo leggero
        CY = CY_beta * beta + cfg.CY_delta_r * delta_r + cfg.CY_p * p_hat

        return {
            'CL': CL,
            'CD': CD,
            'Cm': Cm,
            'Cl': Cl,
            'Cn': Cn,
            'CY': CY,
        }


# ======================================================================
# CONFIGURAZIONI PREDEFINITE
# ======================================================================

def make_c172_config() -> AeroConfig:
    """
    Configurazione aerodinamica tipo Cessna 172.

    Dati approssimativi basati su letteratura aeronautica pubblica.
    CL lineare fino a ~14°, stallo a ~16°, post-stallo con decadimento.
    """
    # Tabella alpha [rad] da -90° a +90°
    # Questo range esteso è necessario per il futuro tailsitter
    alpha_deg = np.array([
        -90, -60, -30, -20, -16, -12, -8, -4, 0,
        4, 8, 12, 14, 16, 18, 20, 30, 60, 90
    ], dtype=float)
    alpha = np.radians(alpha_deg)

    # CL: lineare nella regione centrale, stallo a ~16°,
    # post-stallo verso comportamento flat-plate (CL → sin(2α) ≈ 0 a ±90°)
    CL = np.array([
        0.0, -0.8, -1.2, -0.9, -0.6, -0.3, 0.1, 0.35, 0.25,
        0.5, 0.8, 1.1, 1.3, 1.5, 1.2, 0.9, 0.8, 0.5, 0.0
    ], dtype=float)

    # CD: minimo nella regione di crociera, alto in stallo e a ±90°
    CD = np.array([
        1.8, 1.3, 0.5, 0.15, 0.08, 0.04, 0.03, 0.027, 0.025,
        0.027, 0.032, 0.045, 0.06, 0.12, 0.25, 0.4, 0.8, 1.3, 1.8
    ], dtype=float)

    # Cm: stabile (negativo) nella regione centrale,
    # instabile in post-stallo (tendenza al pitch-up o pitch-down)
    Cm = np.array([
        0.15, 0.1, 0.0, -0.05, -0.08, -0.1, -0.08, -0.06, -0.05,
        -0.06, -0.08, -0.1, -0.12, -0.15, -0.1, -0.05, 0.0, 0.1, 0.15
    ], dtype=float)

    return AeroConfig(
        alpha_table=alpha,
        CL_table=CL,
        CD_table=CD,
        Cm_table=Cm,
        S_ref=16.2,      # m² (C172: 174 ft²)
        b_ref=11.0,      # m (C172: 36 ft)
        c_ref=1.49,      # m (MAC approssimativa)
        CL_delta_e=0.3,
        CD_delta_e=0.01,
        Cm_delta_e=-1.2,
        Cl_delta_a=0.09,
        Cn_delta_r=0.07,
        CY_delta_r=0.15,
        Cm_q=-12.0,
        Cl_p=-0.45,
        Cn_r=-0.12,
    )


def make_generic_config() -> AeroConfig:
    """
    Configurazione generica per test (ala simmetrica semplice).
    Utile per validare il motore senza dati specifici di un velivolo.
    """
    alpha_deg = np.array([-90, -45, -20, -15, -10, -5, 0,
                          5, 10, 15, 20, 45, 90], dtype=float)
    alpha = np.radians(alpha_deg)

    # Ala simmetrica: CL = 0 a alpha = 0
    CL = np.array([0.0, -1.0, -1.1, -0.9, -0.55, -0.28, 0.0,
                   0.28, 0.55, 0.9, 1.1, 1.0, 0.0], dtype=float)

    CD = np.array([1.8, 1.0, 0.2, 0.08, 0.035, 0.012, 0.008,
                   0.012, 0.035, 0.08, 0.2, 1.0, 1.8], dtype=float)

    Cm = np.zeros_like(alpha)  # ala simmetrica: Cm = 0

    return AeroConfig(
        alpha_table=alpha,
        CL_table=CL,
        CD_table=CD,
        Cm_table=Cm,
        S_ref=15.0,
        b_ref=10.0,
        c_ref=1.5,
    )