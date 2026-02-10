from pathlib import Path

import pandas as pd
import numpy as np
from we_function import WE
import matplotlib.pyplot as plt

fileName = str(Path(__file__).with_name("Economics eSAF.xlsx"))

data={
    "econ"  : pd.read_excel(fileName,'eSAF Matlab',usecols='C',skiprows=1,nrows=11).to_numpy(copy=True),
    "real"  : pd.read_excel(fileName,'eSAF Matlab',usecols='F',skiprows=1,nrows=17).to_numpy(copy=True),
    "plant" : pd.read_excel(fileName,'eSAF Matlab',usecols='J',skiprows=1,nrows=20).to_numpy(copy=True),
    "we_matrix" : pd.read_excel(fileName,'Electrolyzer',usecols='J:L',skiprows=3,nrows=6).to_numpy(copy=True),
    "we" : pd.read_excel(fileName,'Electrolyzer',usecols='C',skiprows=3,nrows=3).to_numpy(copy=True),
    "we_type" : str(pd.read_excel(fileName,'Electrolyzer',usecols='C',skiprows=12,nrows=1))}

EE=np.linspace(0, 0.200,1001)
WH=np.linspace(1000, 8700,1001)

LH = np.zeros((len(EE), len(WH)))  # inizializzazione matrice risultati

for i in range(len(EE)):
    for j in range(len(WH)):
        
        data['real'][0]=EE[i]
        data['we'][1]=WH[j]
        LCOH, TOC, SR, ACC, H2_p, Mtn, H2_pwr = WE(data)
        LH[i,j]=LCOH[-1]
        

X, Y = np.meshgrid(WH, EE*1e3 )  # griglia con WH (x) e EE (y) moltiplicata per 1e3
levels = np.arange(2, 26, 1)  # livello da 2 a 25 con passo 1

contour = plt.contour(X, Y, LH, levels=levels, linewidths=2)
plt.clabel(contour, inline=True, fontsize=8, fmt='%1.0f', inline_spacing=10)

plt.xlabel('Operating Hours (h/y)')
plt.ylabel('EE cost (€/MWh)')
plt.title('Levelized Cost of Hydrogen (€/kg)')
plt.grid(True)
plt.tight_layout()
plt.show()