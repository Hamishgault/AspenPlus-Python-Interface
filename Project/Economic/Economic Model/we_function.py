#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 24 13:40:45 2025

@author: Alessio
"""
import numpy as np

def WE(data):
    
    
    PP=data['we'][0]  #Installed Power (MW)
                
    WH=data['we'][1]  #Working hours (h/y)
                    
    Use=data['we'][2] #Average  WE power / Max Power (%)
        
    WACC=data['econ'][10]
        
    H2_pwr=PP*WH*Use # MWh/y
        
    Py=data['econ'][6]
        
    N=2050-Py-1
    
    DATA=data['we_matrix'][:,1]
        
    Mtn=DATA[5]
    
    Tot_WH=N*WH   #Total working hours (h)
    
    NR=np.ceil(Tot_WH/DATA[2])-1;  #number of stack replacements
    
    SD=np.floor(DATA[3]/WH) #stack duration (years)
    
    Avg_P=DATA[1]+DATA[2]/2000*DATA[3]*DATA[1];
    
    TOC = PP * DATA[0] * 1e3  # Total Overnight Cost (€)
    
    SR = NR * DATA[4] * TOC   # Stack replacement cost (€)
    
    ACC = TOC * WACC * (1 + WACC)**N / ((1 + WACC)**N - 1)  # Annual Capital Cost (€)
    
    El_c = PP * WH * Use * data['real'][0] * 1e3  # Electricity Expense (€/y)
    
    H2_p = PP * WH * Use / Avg_P / 1e3  # H2 production (kton/y)
    
    CAPEX = ACC / H2_p / 1e6  # CAPEX (€/kg)
    
    EE = El_c / H2_p / 1e6  # Electricity (€/kg)
    
    Stack = SR / H2_p / N / 1e6  # Stack Replacement (€/kg)
    
    OPEX = TOC * DATA[5] / H2_p / 1e6  # OPEX (€/kg)
    
    TOT = CAPEX + EE + Stack + OPEX  # Total H2 Cost (€/kg)
    
    LCOH =[x.item() for x in [CAPEX, EE, Stack, OPEX, TOT]]
    
    return LCOH,TOC,SR,ACC,H2_p,Mtn,H2_pwr

