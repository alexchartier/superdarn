import numpy as np
import os 
import sys
import datetime as dt
import matplotlib.pyplot as plt
import pdb


def main():
    inFname = 'data/meteorwind/2020/01/2020Jan01.fhw.txt'
    data = loadWinds(inFname)
    plt.plot(data['time'], data['Vm'], '-x')
    plt.ylabel('Meridional Wind (m/s) at %1.1f N, %1.1f E' % (data['Vm_lat'][0], data['Vm_long'][0]))
    plt.xlabel('Time (UT)')
    
    plt.show()
    

def loadWinds(inFname):
    with open(inFname, 'r') as f:
        txt = f.readlines()

    for ind, line in enumerate(txt):
        if line[0] == '#':
            hdr = line.split()
            if len(hdr) > 5:
                hdr = ['time',] +  hdr[5:]
                data = {}
                for el in hdr:
                    data[el] = []
        else:
            timeVals = [int(el) for el in line.split()[:4]] + [0,]
            dataVals = [float(el) for el in line.split()[4:]]
            data['time'].append(dt.datetime(*timeVals))
            for ind2, valName in enumerate(hdr[1:]):
                data[valName].append(dataVals[ind2])
    return data
if __name__ == '__main__':
    main()    
