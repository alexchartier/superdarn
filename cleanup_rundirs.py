# Clear out the old run directories

import os.path
import time
import glob
import numpy as np
import shutil
import sys
import pdb

target = sys.argv[1]
cutoff = 86400
dirs = [d for d in os.listdir(
    './%s' % target) if os.path.isdir(os.path.join('./%s' % target, d))]

for dn in dirs:
    dirn = os.path.join(target, dn)
    flist = glob.glob(os.path.join(dirn, '*'))
    if len(flist) == 0:
        os.rmdir(dirn)
    else:
        latest_file = max(flist, key=os.path.getctime)
        modtime = time.time() - os.path.getmtime(latest_file)

        if modtime > 86400:
            shutil.rmtree(dirn)
            print('%s removed' % dirn)
        else:
            print('%s active - see %s' % (dirn, latest_file))
