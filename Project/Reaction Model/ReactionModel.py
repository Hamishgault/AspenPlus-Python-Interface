# rwgs_ft_model.py
# Fe-catalyzed CO2 hydrogenation: RWGS + FT kinetics (engineering model)
# Author: (you)
# License: MIT
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

R = 8.314462618  # J/mol/K

# -----------------------------
# Helpers: Arrhenius & van't Hoff
# -----------------------------
def arrhenius(k0: float, Ea: float, T: np.ndarray | float) -> np.ndarray:
    """
    k(T) = k0 * exp(-Ea / (R*T))
    k0 in rate units (e.g., mol/(kg_cat*s*bar^2) depending on rate law)
    Ea in J/mol, T in K
    """
    T = np.asarray(T, dtype=float)
    return k0 * np.exp(-Ea / (R * T))


def vanthoff_K(K_ref: float, dH_ads: float, T: np.ndarray | float, T_ref: float = 298.15) -> np.ndarray:
    """
    Temperature dependence of adsorption constant (equilibrium constant) via van't Hoff:
    K(T) = K_ref * exp( -ΔH_ads/R * (1/T - 1/T_ref) )
    dH_ads < 0 for exothermic adsorption (common).
    Units of K are whatever K_ref has (e.g., 1/bar).
    """
    T = np.asarray(T, dtype=float)
    return K_ref * np.exp(-(dH_ads / R) * (1.0 / T - 1.0 / T_ref))


# -----------------------------
# Parameter containers
# -----------------------------
@dataclass
class RWGSParams:
    # Kinetic parameters
    k0_f: float          # forward pre-exponential
    Ea_f: float          # forward activation energy [J/mol]
    # Optional reverse (if you want explicit k_rev). Otherwise use Keq to enforce detailed balance.
    k0_r: float | None = None
    Ea_r: float | None = None

    # Adsorption constants at reference temperature and heats (optional)
    Kco2_ref: float = 0.5     # 1/bar
    dH_co2: float = -40e3     # J/mol (example)
    Kco_ref: float = 0.5      # 1/bar
    dH_co: float = -60e3
    Kh2_ref: float = 0.05     # 1/bar (dissociative adsorption is typically weak in LHHW fits)
    dH_h2: float = -10e3
    Kh2o_ref: float = 0.2     # 1/bar
    dH_h2o: float = -30e3
    T_ref: float = 298.15

    # Denominator exponent (1 or 2 depending on the mechanistic derivation)
    denom_power: int = 2


@dataclass
class FTParams:
    # Arrhenius for initiation, propagation, termination
    ki0: float
    Eai: float
    kp0: float
    Eap: float
    kt0: float
    Eat: float


# -----------------------------
# Equilibrium term for RWGS
# -----------------------------
def ln_Keq_rwgs_vant_hoff(T: np.ndarray | float, A: float, B: float) -> np.ndarray:
    """
    Flexible two-parameter ln(Keq) = A + B/T form.
    Provide A, B from your thermodynamic fit (do this from NASA/JanAF or your dataset).
    """
    T = np.asarray(T, dtype=float)
    return A + B / T


# -----------------------------
# RWGS rate (LHHW form)
# -----------------------------
def rwgs_rate(
    T: np.ndarray | float,
    pco2: np.ndarray | float,
    ph2: np.ndarray | float,
    pco: np.ndarray | float,
    ph2o: np.ndarray | float,
    pars: RWGSParams,
    lnKeq_func=None,
    lnKeq_args: tuple = (),
) -> np.ndarray:
    """
    LHHW RWGS rate:
    r = k(T) * ( pCO2*PH2 - (pCO*pH2O)/Keq(T) ) / ( 1 + K_CO2 pCO2 + K_CO pCO + K_H2 pH2 + K_H2O pH2O )^n

    - If lnKeq_func is None, the reverse term is dropped (pure forward driving force).
      Prefer providing Keq(T) so the rate respects equilibrium.
    - Adsorption constants are temperature dependent via van't Hoff.
    """
    T = np.asarray(T, dtype=float)
    pco2 = np.asarray(pco2, dtype=float)
    ph2 = np.asarray(ph2, dtype=float)
    pco = np.asarray(pco, dtype=float)
    ph2o = np.asarray(ph2o, dtype=float)

    kf = arrhenius(pars.k0_f, pars.Ea_f, T)

    # Adsorption terms
    Kco2 = vanthoff_K(pars.Kco2_ref, pars.dH_co2, T, pars.T_ref)
    Kco  = vanthoff_K(pars.Kco_ref,  pars.dH_co,  T, pars.T_ref)
    Kh2  = vanthoff_K(pars.Kh2_ref,  pars.dH_h2,  T, pars.T_ref)
    Kh2o = vanthoff_K(pars.Kh2o_ref, pars.dH_h2o, T, pars.T_ref)

    denom = (1.0 + Kco2 * pco2 + Kco * pco + Kh2 * ph2 + Kh2o * ph2o) ** pars.denom_power

    if lnKeq_func is None:
        driving = pco2 * ph2  # forward only (use with care)
    else:
        lnKeq = lnKeq_func(T, *lnKeq_args)
        Keq = np.exp(lnKeq)
        driving = pco2 * ph2 - (pco * ph2o) / Keq

    r = kf * driving / denom

    # Optional explicit reverse using k_r (not necessary if using Keq)
    if (pars.k0_r is not None) and (pars.Ea_r is not None) and (lnKeq_func is None):
        kr = arrhenius(pars.k0_r, pars.Ea_r, T)
        r = kf * pco2 * ph2 / denom - kr * pco * ph2o / denom

    return r  # rate in whatever units are implied by kf and pressures


# -----------------------------
# FT kinetics: total carbon rate and ASF distribution
# -----------------------------
def ft_rates_and_alpha(
    T: np.ndarray | float,
    pco: np.ndarray | float,
    pars: FTParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
      r_FT_total = r_initiation = ki(T) * pCO        [mol C/(kg_cat*s)]
      ki(T), kp(T), kt(T), alpha(T)                  [-]
    Alpha is defined as kp / (kp + kt).
    """
    T = np.asarray(T, dtype=float)
    pco = np.asarray(pco, dtype=float)

    ki = arrhenius(pars.ki0, pars.Eai, T)
    kp = arrhenius(pars.kp0, pars.Eap, T)
    kt = arrhenius(pars.kt0, pars.Eat, T)

    alpha = kp / (kp + kt)
    r_FT = ki * pco
    return r_FT, ki, kp, kt, alpha


def asf_weights(alpha: np.ndarray | float, n_max: int = 20) -> np.ndarray:
    """
    Anderson–Schulz–Flory (ASF) chain-length distribution weights for n=1..n_max (molar basis).
    w_n = (1 - alpha) * alpha^(n-1), independent for each alpha (can be array).
    Returns shape (len(alpha), n_max) if alpha is array; else (n_max,).
    """
    alpha = np.asarray(alpha, dtype=float)
    if alpha.ndim == 0:
        n = np.arange(1, n_max + 1)
        return (1.0 - alpha) * alpha ** (n - 1)

    n = np.arange(1, n_max + 1)[None, :]
    return (1.0 - alpha[:, None]) * alpha[:, None] ** (n - 1)


# -----------------------------
# Lumped source terms (optional convenience)
# -----------------------------
def source_terms(
    T: np.ndarray | float,
    pco2: np.ndarray | float,
    ph2: np.ndarray | float,
    pco: np.ndarray | float,
    ph2o: np.ndarray | float,
    rwgs_pars: RWGSParams,
    ft_pars: FTParams,
    lnKeq_func=None,
    lnKeq_args: tuple = (),
    n_max: int = 20,
):
    """
    Compute species source terms (mol/(kg_cat*s)) for a homogeneous catalytic zone:
    RWGS: CO2 + H2 <-> CO + H2O
      s_CO2 = -r_rwgs
      s_H2  = -r_rwgs
      s_CO  = +r_rwgs
      s_H2O = +r_rwgs

    FT (carbon accounting):
      r_FT_total = ki(T)*pCO  [mol C/(kg*s)] consumes CO and H2 per stoichiometry ~ CO + 2H -> CH2(s)
      Here we consume CO at rate r_FT_total and H2 at 2*r_FT_total (simplified).
      Product split by ASF weights for n=1..n_max (you can re-map to species as you prefer).

    Returns dict with:
      - r_rwgs
      - r_ft_total, alpha, weights (ASF)
      - s_CO2, s_H2, s_CO, s_H2O  (including both RWGS and FT)
      - carbon_chain_weights (ASF array)
    """
    r_rwgs = rwgs_rate(T, pco2, ph2, pco, ph2o, rwgs_pars, lnKeq_func, lnKeq_args)
    r_ft_total, ki, kp, kt, alpha = ft_rates_and_alpha(T, pco, ft_pars)
    w = asf_weights(alpha, n_max=n_max)  # distribution for C1..C_n

    # Species source terms (lumped stoichiometry)
    s_CO2 = -r_rwgs
    s_H2  = -r_rwgs - 2.0 * r_ft_total
    s_CO  = +r_rwgs - r_ft_total
    s_H2O = +r_rwgs

    return dict(
        r_rwgs=r_rwgs,
        r_ft_total=r_ft_total,
        alpha=alpha,
        weights=w,
        s_CO2=s_CO2,
        s_H2=s_H2,
        s_CO=s_CO,
        s_H2O=s_H2O,
        ki=ki, kp=kp, kt=kt,
    )


# -----------------------------
# Example Keq(T) hook (fill with your own parameters)
# -----------------------------
class KeqRWGS:
    """
    Simple wrapper to provide Keq(T) to rwgs_rate.
    Set A, B so ln(Keq) = A + B/T fits your thermodynamic data.
    """
    def __init__(self, A: float, B: float):
        self.A = A
        self.B = B

    def lnKeq(self, T):
        return ln_Keq_rwgs_vant_hoff(T, self.A, self.B)