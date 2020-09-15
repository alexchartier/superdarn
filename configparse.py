"""
configparse.py

Handle configuration files

Author: Alex T. Chartier, Johns Hopkins Applied Physics Laboratory, 2018 
"""

import pdb
import os
import glob
import netCDF4
import datetime as dt
from configparser import ConfigParser, SafeConfigParser

#### Configuration routines ####

def configure_system(config_fname):
    assert os.path.isfile(config_fname), "Error: config file does not exist - %s" % config_fname
    config = SafeConfigParser(os.environ)
    config.read(config_fname)

    sysconfig = {}
    for section in config.sections():
        sysconfig[section] = {}
        for k in config._sections[section].keys():
            sysconfig[section][k] = config.get(section, k)
    entries = [e[0] for e in list(sysconfig.items())]

    # Convert things to float, int, list, fullpath from strings
    for e in entries:
        sysconfig[e] = dictstr2num(sysconfig[e])
        sysconfig[e] = dictsplit(sysconfig[e])
        sysconfig[e] = dictfullpath(sysconfig[e])
        for key, val in sysconfig[e].items():
            try:
                sysconfig[e][key] = [float(v) for v in val]
            except:
                None

    for k, v in sysconfig['global'].items():
        if k == 'kp': 
            sysconfig['global'][k] = [int(kpi) for kpi in v]
        try:
            if len(v) == 5: 
                sysconfig['global'][k] = get_datetime(v)
        except:
            None
        try:
            sysconfig['global'][k] = ast.literal_eval(v)
        except:
            None
    sysconfig['global']['timestep'] = dt.timedelta(minutes=sysconfig['global']['timestep'])
 
    if 'out_fnames' in sysconfig.keys(): 
        try: 
            for k, v in sysconfig['out_fnames'].items(): 
                dn, _ = os.path.split(v)
                os.makedirs(dn, exist_ok=True) 
        except:
            print('Could not make out_fnames dirs')

    for k, v in sysconfig['dirs'].items(): 
        try: 
            os.makedirs(v, exist_ok=True) 
        except:
            print('Could not make %s dir: %s' % (k, v))

    return sysconfig


def get_datetime(time_list):
    time_list = [int(st) for st in time_list]
    return dt.datetime(time_list[0], time_list[1], time_list[2], time_list[3], time_list[4])


def dictsplit(dictionary):
    for key, val in dictionary.items():
        try:
            if ',' in val:
                dictionary[key] = [v.strip(" ") for v in val.split(',')]
        except:
            None
    return dictionary


def dictstr2num(dictionary):
    for key, val in dictionary.items():
        try:
            dictionary[key] = int(val)
        except:
            try:
                dictionary[key] = float(val)
            except:
                None
    return dictionary


def dictfullpath(dictionary):
    for key, val in dictionary.items():
        try:
            if '/' in val:
                val = os.path.abspath(val)
                dictionary[key] = val
        except:
            None
    return dictionary


def print_box(txt):
    print('\n')
    print('*' * (len(txt) + 4))
    print('* %s *' % txt)
    print('*' * (len(txt) + 4))
    print('\n')


def sysconfig_to_str(sysconfig):
    sysconfig_str = '[global]\n\n' + dict_to_str(sysconfig)
    return sysconfig_str


def dict_to_str(input_dict):
    str_out = ''
    dicts = {}
    for key, val in input_dict.items():
        if isinstance(val, dict):
            dicts[key] = val
        else:
            str_out += '%s: %s\n' % (key, str(val))

    for key, val in dicts.items():
        str_out += '\n\n[%s]\n\n%s' % (key, dict_to_str(val))
    return str_out


if __name__ == "__main__":
    if len(sys.argv) == 2:
        config_fname = sys.argv[-1]
        main(config_fname)
    else:
        main()


