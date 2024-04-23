import pdb
import numpy as np
import struct

fn = 'data/cfit/2020/01/20200131.wal.cfit'
hdr_format = {
    'version.major': 'h',
    'version.minor': 'h',
    'time unix': 'd',
    'station id': 'h',
    'scan flag': 'h',
    'program id': 'h',
    'beam number': 'h',
    'beam az': 'f',
    'channel': 'h',
    'integration time (sec)': 'h',
    'integration time (microsec)': 'h',
    'dist to range0 (km)': 'h',
    'rsep (km)': 'h',
    'risetime (microsec)': 'h',
    'freq (kHz)': 'h',
    'noise': 'i',
    'attenuation': 'h',
    'n avg': 'h',
    'n range gates': 'h',
    'n ranges stored': 'x',
}
# followed by m range table and n data table

lv = [h for h in hdr_format.values()]
fmt = '<' + ''.join(lv)
HDR_SIZE = fmt.count('h') * 2 + fmt.count('x') * 1 + \
    fmt.count('i') * 4 + fmt.count('f') * 4 + fmt.count('d') * 8
with open(fn, 'rb') as f:
    data = struct.unpack(fmt, f.read(HDR_SIZE))
    pdb.set_trace()
