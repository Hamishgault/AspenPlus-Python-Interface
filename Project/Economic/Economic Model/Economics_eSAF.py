#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 24 14:56:03 2025

@author: Alessio
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import minimize
from we_function import WE

fileName="Economics eSAF.xlsx"

data={ 
      "econ"  : pd.read_excel(fileName,'eSAF Matlab',usecols='C',skiprows=1,nrows=11).to_numpy(),
      "real"  : pd.read_excel(fileName,'eSAF Matlab',usecols='F',skiprows=1,nrows=17).to_numpy(),
      "plant" : pd.read_excel(fileName,'eSAF Matlab',usecols='J',skiprows=1,nrows=20).to_numpy(),
      "we_matrix" : pd.read_excel(fileName,'Electrolyzer',usecols='J:L',skiprows=3,nrows=6).to_numpy(),
      "we" : pd.read_excel(fileName,'Electrolyzer',usecols='C',skiprows=3,nrows=3).to_numpy(),
      "we_type" : str(pd.read_excel(fileName,'Electrolyzer',usecols='C',skiprows=12,nrows=1))}


def val(data,DF=data['econ'][10].item(),ReFuel=data['real'][16].item()):
    
    
    LCOH, TOC, SR, ACC, H2_p, Mtn, H2_pwr = WE(data)
    
    TOC_FT=150e3
    TOC_AtJ=240e3
    
    CAPEX=data['plant'][0].item()
    
    d_e=data['econ'][0].item()
    dr=data['econ'][1].item()
    dp=int(data['econ'][2])
    DeP_n=int(data['econ'][3])
    infl=data['econ'][4].item()
    tax=data['econ'][5].item()
    
    EE=data['real'][0].item()
    cambio=data['real'][1].item()
    conv=data['real'][2].item()
    BRENT=data['real'][3].item()
    ETS1 = data['real'][10].item()
    ETS2 = data['real'][11].item()
    DIFF_LPG = data['real'][4].item()
    DIFF_NAPTHA = data['real'][5].item()
    DIFF_KERO = data['real'][6].item()
    DIFF_DIESEL = data['real'][7].item()
    DIFF_WAX = data['real'][8].item()
    Met = data['real'][9].item()
    CC = data['real'][12].item()
    
    CO2_feed = data['plant'][1].item()      # ktonCO2/ktonH2
    CO2_compr = data['plant'][2].item()     # MWh/ktonCO2
    H2_feed = data['plant'][3].item()       # MWH/y
    H2_compr = data['plant'][4].item()      # MWh/ktonH2
    Pwr = data['plant'][5].item()           # MWh/ktonH2
    Heat = data['plant'][6].item()          # -
    Operatori = data['plant'][7].item()     # k€/y
    Overhead = data['plant'][8].item()      # k€/y
    Manutenzione = data['plant'][9].item()  # %
    CO2_out = data['plant'][10].item()      # ktonCO2/ktonH2
    Naptha_mass = data['plant'][11].item()  # kton/ktonH2
    Naptha_CO2 = data['plant'][12].item()   # ktonCO2/ktonH2
    Naptha_GJ = data['plant'][13].item()    # -
    Kero_mass = data['plant'][14].item()    # kton/ktonH2
    Kero_CO2 = data['plant'][15].item()     # ktonCO2/ktonH2
    Kero_GJ = data['plant'][16].item()      # -
    Diesel_mass = data['plant'][17].item()  # kton/ktonH2
    Diesel_CO2 = data['plant'][18].item()   # ktonCO2/ktonH2
    Diesel_GJ = data['plant'][19].item()    # -
    
    Py = int(data['econ'][6])
    
    N=2050-Py
       
    n = np.arange(N+1)
    
    y=np.arange(Py,2051)             
           
    DF_n = (1 + DF) ** n
    infl_n = (1 + infl) ** n
    
    
    def replicate(val):
        return np.ones(N + 1) * val
    
    
    def payper(rate, nper, pv):
        """
        Calcola la rata annuale costante (annuity) per ripagare un prestito.
    
        Parameters:
        - rate: tasso di interesse annuo (es. 0.08 per 8%)
        - nper: numero totale di periodi (es. anni)
        - pv: valore presente (es. capitale da rimborsare)
    
        Returns:
        - pagamento annuo (float)
        """
        if rate == 0:
            return pv / nper
        else:
            return pv * rate * (1 + rate) ** nper / ((1 + rate) ** nper - 1)
    
    
   
    
    
    EE_n = replicate(EE)
    cambio_n = replicate(cambio)
    BRENT_n = replicate(BRENT)
    
    ETS1_n = replicate(ETS1)
    ETS2_n = replicate(ETS2)
    DIFF_LPG_n = replicate(DIFF_LPG)
    DIFF_NAPTHA_n = replicate(DIFF_NAPTHA)
    DIFF_KERO_n = replicate(DIFF_KERO)
    DIFF_DIESEL_n = replicate(DIFF_DIESEL)
    DIFF_WAX_n = replicate(DIFF_WAX)
    Met_n = replicate(Met)
    CC_n = replicate(CC)
    ReFuel_n = replicate(ReFuel)
    
    Exp = np.zeros((13, N + 1))
    Rev = np.zeros((10, N + 1))
    Loan = np.zeros((4, N + 1))
    Dep = np.zeros(N + 1)
    Tax = np.zeros((2, N + 1))
    CF = np.zeros((4, N + 1))
    
    x = int(np.where(y == 2030)[0][0])
    
    # RED credits
    RED_b = LCOH[-1] * 1000 / 3 - (BRENT_n[x] + DIFF_NAPTHA_n[x]) * conv
    RED_d = LCOH[-1] * 1000 / 3 - (BRENT_n[x] + DIFF_DIESEL_n[x]) * conv
    RED_k = LCOH[-1] * 1000 / 2 - (BRENT_n[x] + DIFF_KERO_n[x]) * conv * 1.5
        
    #RED_b = 2200 - (BRENT_n[x] + DIFF_NAPTHA_n[x]) * conv
    #RED_d = 2200 - (BRENT_n[x] + DIFF_DIESEL_n[x]) * conv
    #RED_k = 2500 - (BRENT_n[x] + DIFF_KERO_n[x]) * conv * 1.5     
        
    RED_k_n = replicate(RED_k)
    RED_b_n = replicate(RED_b)
    RED_d_n = replicate(RED_d)
    
    # Spese
    Exp[0, x:] = H2_p * CO2_feed * CC_n[x:]
    Exp[1, x:] = H2_p * CO2_feed * CO2_compr * EE_n[x:]
    Exp[2, x:] = H2_pwr * EE_n[x:]
    Exp[3, x:] = H2_p * H2_compr * EE_n[x:]
    Exp[4, x:] = H2_p * Pwr * EE_n[x:]
    Exp[5, x:] = H2_p * Heat * Met_n[x:]
    
    Exp[8, x:] = Operatori
    Exp[9, x:] = Manutenzione * TOC_FT + SR / (N - 1) / 1e3 + TOC * Mtn / 1e3
    Exp[10, x:] = Overhead
    Exp[11, x:] = H2_p * CO2_out * ETS1_n[x:]
    Exp[12, x - 1] = (1 - d_e) * CAPEX
    
    Tot_Exp = np.sum(Exp, axis=0)
    
    # Ricavi
    Rev[0, x:] = Naptha_mass * H2_p * (BRENT_n[x:] + DIFF_NAPTHA_n[x:]) * conv
    Rev[1, x:] = Naptha_CO2 * H2_p * ETS2_n[x:]
    Rev[2, x:] = Naptha_mass * H2_p * RED_b_n[x:]
    
    Rev[3, x:] = Kero_mass * H2_p * (BRENT_n[x:] + DIFF_KERO_n[x:]) * conv
    Rev[4, x:] = Kero_CO2 * H2_p * ETS1_n[x:]
    Rev[5, x:] = Kero_mass * H2_p * RED_k_n[x:]
    Rev[6, x:] = Kero_mass * H2_p * ReFuel_n[x:]
    
    Rev[7, x:] = Diesel_mass * H2_p * (BRENT_n[x:] + DIFF_DIESEL_n[x:]) * conv
    Rev[8, x:] = Diesel_CO2 * H2_p * ETS2_n[x:]
    Rev[9, x:] = Diesel_mass * H2_p * RED_d_n[x:]
    
    Tot_Rev = np.sum(Rev, axis=0)
    P_L = Tot_Rev - Tot_Exp
    
    # Prestito
    Loan[0, x:x + dp] = payper(dr, dp, CAPEX * d_e)
    Loan[1, :] = CAPEX * d_e
    
    for j in range(x, N + 1):
        if Loan[1, j - 1] > 0:
            Loan[2, j] = Loan[1, j - 1] * dr
            Loan[3, j] = Loan[0, j] - Loan[2, j]
            Loan[1, j] = Loan[1, j - 1] - Loan[3, j]
    
    Dep[x:x + DeP_n] = CAPEX / DeP_n
    
    Tax[0, :] = Tot_Rev - Tot_Exp - Dep - Loan[2, :]
    Tax[0, Tax[0, :] < 0] = 0
    Tax[1, x:] = Tax[0, x:] * tax
    
    OCF = Tot_Rev - Tot_Exp - Loan[0, :] - Tax[1, :]
    DCF = OCF / DF_n
    
    CCF = np.zeros(N + 1)
    CCF[0] = DCF[0]
    for j in range(1, N + 1):
        CCF[j] = CCF[j - 1] + DCF[j]
    
    VAN = CCF[-1]
    
    RES = np.vstack([Exp, Rev, Loan, Dep[np.newaxis], Tax, DF_n[np.newaxis], OCF[np.newaxis], DCF[np.newaxis], CCF[np.newaxis]])
    
    Kero = Rev[3:7, x] / (Kero_mass * H2_p)
    Diesel_k = Rev[7:10, x] / (Kero_mass * H2_p)
    Naphta_k = Rev[0:3, x] / (Kero_mass * H2_p)
    
    Ex = np.zeros(10)
    Ex[0] = np.sum(RES[0:2, 1])
    Ex[1] = np.sum(RES[2:4, 1])
    Ex[2] = RES[4, 1]
    Ex[3] = RES[5, 1]
    Ex[4] = np.sum(RES[[8, 10], 1])
    Ex[5] = RES[9, 1]
    Ex[6] = RES[11, 1]
    
    ACC = (np.sum(Kero) + np.sum(Naphta_k) + np.sum(Diesel_k) - np.sum(Ex[0:7]) / (Kero_mass * H2_p)) * Kero_mass * H2_p
    Ex[7] = ACC
    Ex[8] = np.sum(RES[0:13, 1]) + ACC
    
    COP = Ex / (Kero_mass * H2_p)
    Sell_Price_k = np.array([np.sum(Kero), np.sum(Naphta_k), np.sum(Diesel_k)])
    err = abs(VAN)
    
    str_labels = [
        'n', 'year', 'CO2 feed', 'CO2 compression', 'H2 production', 'H2 compression',
        'Power', 'Heating', 'CW', 'Steam', 'Operator', 'Maintenance', 'Overhead',
        'CO2 ETS', 'FCI', 'Naphta Fossil', 'Naphtha ETS', 'Naphtha RED', 'Kero Fossil',
        'Kero ETS', ' Kero RED', 'Kero ReFuel', 'Diesel Fossil', 'Diesel ETS',
        'Diesel RED', 'Loan Annuity', 'Residual Debt', 'Interests', 'Principal Rep',
        'Dep', 'Profit', 'Tax', 'DF', 'OCF', 'DCF', 'CCF'
    ]
    
    T = pd.DataFrame(data=np.vstack([n, y, RES]), index=str_labels).T
    

    
    return err,VAN,T,COP,Kero,LCOH,Sell_Price_k
    

r_IRR = minimize(lambda DF: val(data, DF, data['real'][16].item())[0],0.01,method='Nelder-Mead')     
r_BEP= minimize(lambda ReFuel: val(data, data['econ'][10].item(), ReFuel)[0],5000,method='Nelder-Mead')             
    
IRR=r_IRR.x 
BEP=r_BEP.x  


err,VAN,T,COP,Kero,LCOH,Sell_Price_k=val(data,ReFuel=BEP)


bottom = 0
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
labels = ['Fossil', 'ETS', 'RED', 'ReFuel']

for i in range(len(Kero)):
    plt.bar('Kerosene', Kero[i], bottom=bottom, color=colors[i], label=labels[i])
    bottom += Kero[i]

plt.ylabel('Price €/ton')
plt.title('Market Price')
plt.legend()
    
    