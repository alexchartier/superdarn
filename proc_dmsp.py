import numpy as np
import h5py
import datetime as dt

def main(
    fn = 'data/dmsp/dms_ut_20140523_16.002.hdf5',
):
    #flist = get_file_list(data_dir)
    #for fn in flist:
    raw_dmsp_data = load_data(fn)
    processed_dmsp_data = proc_data(raw_dmsp_data)

def load(fn):
    return proc_data(load_data(fn))


def load_data(fn):
    with h5py.File(fn, "r") as f:
        # Get the metadata
        parameters = f.get('Metadata')['Data Parameters'][...]
        # Get the data
        dataTable = f.get('Data').get('Table Layout')[...]

    vars = {}
    out = {}
    for ind, prm in enumerate(parameters):
        str = prm[0].decode('utf-8')  # removing those annoying b' prefixes
        vars[str] = ind 
        out[str] = []
    
    for entry in dataTable:
        for k, v in out.items():
            v.append(entry[vars[k]])

    for k, v in out.items():
        out[k] = np.array(v)
    return out


def proc_data(dmsp_data):

    # remove flagged bad data

    forQualIndex = dmsp_data["ION_V_FOR_FLAG"] == 1
    leftQualIndex = dmsp_data["ION_V_LEFT_FLAG"] == 1
    qualFlag = forQualIndex & leftQualIndex

    #goodInd = np.logical_and(dmsp_data['RPA_FLAG_UT'] < 2, dmsp_data['IDM_FLAG_UT'] < 2)  # NOTE: This is only for F15
    for k, v in dmsp_data.items():
        dmsp_data[k] = v[qualFlag]
    dmsp_data['Time'] = []

    # Store values
    for ind, yr in enumerate(dmsp_data['YEAR']):
        time = dt.datetime(
            yr, dmsp_data['MONTH'][ind], dmsp_data['DAY'][ind], dmsp_data['HOUR'][ind], 
            dmsp_data['MIN'][ind], dmsp_data['SEC'][ind],
        )
        dmsp_data['Time'].append(time)

    return dmsp_data
    

if __name__ == '__main__':
    main() 











