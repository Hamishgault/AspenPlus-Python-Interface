#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 24 13:40:45 2025

@author: Alessio
"""
import numpy as np

ECON_IDX = {
    "WACC": 10,
    "Py": 6,
}
REAL_IDX = {
    "EE": 0,
}


def get_scalar(data, section, key):
    idx_map = {
        "econ": ECON_IDX,
        "real": REAL_IDX,
    }
    return data[section][idx_map[section][key]].item()

def WE(data):
    """Compute electrolyzer costs and production metrics."""
    PP = data['we'][0].item()  # Installed Power (MW)

    WH = data['we'][1].item()  # Working hours (h/y)

    Use = data['we'][2].item()  # Average WE power / Max Power (%)

    WACC = get_scalar(data, "econ", "WACC")

    H2_pwr=PP*WH*Use # MWh/y
        
    Py = get_scalar(data, "econ", "Py")
        
    N=2050-Py-1
    
    DATA=data['we_matrix'][:,1]
        
    Mtn=DATA[5]
    
    Tot_WH=N*WH   #Total working hours (h)
    
    NR = max(0, np.ceil(Tot_WH / DATA[2]) - 1)  # number of stack replacements
    
    SD=np.floor(DATA[3]/WH) #stack duration (years)
    
    Avg_P=DATA[1]+DATA[2]/2000*DATA[3]*DATA[1];
    
    TOC = PP * DATA[0] * 1e3  # Total Overnight Cost (€)
    
    SR = NR * DATA[4] * TOC   # Stack replacement cost (€)
    
    if WACC == 0:
        ACC = TOC / N
    else:
        ACC = TOC * WACC * (1 + WACC) ** N / ((1 + WACC) ** N - 1)  # Annual Capital Cost (€)
    
    El_c = PP * WH * Use * get_scalar(data, "real", "EE") * 1e3  # Electricity Expense (€/y)
    
    H2_p = PP * WH * Use / Avg_P / 1e3  # H2 production (kton/y)
    
    CAPEX = ACC / H2_p / 1e6  # CAPEX (€/kg)
    
    EE = El_c / H2_p / 1e6  # Electricity (€/kg)
    
    Stack = SR / H2_p / N / 1e6  # Stack Replacement (€/kg)
    
    OPEX = TOC * DATA[5] / H2_p / 1e6  # OPEX (€/kg)
    
    TOT = CAPEX + EE + Stack + OPEX  # Total H2 Cost (€/kg)
    
    LCOH =[x.item() for x in [CAPEX, EE, Stack, OPEX, TOT]]
    
    return LCOH,TOC,SR,ACC,H2_p,Mtn,H2_pwr

