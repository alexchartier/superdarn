import numpy as np
import os
import sys
import datetime as dt
import matplotlib.pyplot as plt
import glob
import pdb


def main(
    inFnameFmt='data/meteorwind/%Y/%m/%Y%b%d.*.txt',
    startTime=dt.datetime(2020, 1, 1),
    endTime=dt.datetime(2020, 1, 3),
    lonlim=[-140, -80],
    latlim=[20, 80],
    ylim=[-75, 75]),


):
    # Load data
    fList= glob.glob(startTime.strftime(inFnameFmt))
    radarList= []
    for f in fList:
        radarList.append('.'.join(os.path.basename(f).split('.')[1:-1]))
    data= {}
    for radar in radarList:
        inFnameFmt_r= inFnameFmt.replace('*', radar)
        data[radar]= loadRadar(inFnameFmt_r, startTime, endTime)

    # Filter out lons, lats
    poplist= []
    for k, v in data.items():
        if (v['Vm_lat'][0] < latlim[0] or v['Vm_lat'][0] > latlim[1]) or \
    (v['Vm_long'][0] < lonlim[0] or v['Vm_long'][0] > lonlim[1]):
    print('popping %s' % k)
    poplist.append(k)
    for k in poplist:
        data.pop(k)

    # plot
    fig, ax= plt.subplots(len(data), 1)
    ct= 0
    for k, v in data.items():
        ax[ct].plot(v['time'], v['Vm'], '-x')
        ax[ct].set_ylim(ylim)
        ax[ct].set_ylabel(
     '%s\nMer. Wd. (m/s) \n@ %1.0f N, %1.0f E' \
      % (k, v['Vm_lat'][0], v['Vm_long'][0])
      )
       if ct == len(data):
       ax[ct].set_xlabel('Time (UT)')
       ax[ct].grid()
       ct += 1

       plt.show()


       def loadRadar(inFnameFmt, startTime, endTime):
            # loop over times
            time= startTime
            while time < endTime:
            inFname = time.strftime(inFnameFmt)
            if time == startTime:
            data= loadWinds(inFname)
            else:
            data_t= loadWinds(inFname)
       for k, v in data_t.items():
       data[k] += v
       time += dt.timedelta(days=1)
       return data


            def loadWinds(inFname):
            with open(inFname, 'r') as f:
            txt = f.readlines()

            for ind, line in enumerate(txt):
            if line[0] == '#':
            hdr= line.split()
            if len(hdr) > 5:
            hdr= ['time',] +  hdr[5:]
            data= {}
            for el in hdr:
            data[el]= []
       else:
       timeVals = [int(el) for el in line.split()[:4]] + [0,]
            dataVals= [float(el) for el in line.split()[4:]]
            data['time'].append(dt.datetime(*timeVals))
            for ind2, valName in enumerate(hdr[1:]):
       data[valName].append(dataVals[ind2])
       return data


            if __name__ == '__main__':
            main()
