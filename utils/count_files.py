import glob
import os
import numpy as np
import pdb
in_dir = '/project/superdarn/alex/cfit/'

for root, dir, files in os.walk(in_dir):
    dir.sort()
    cnt = np.sum(len(files))
    if cnt > 0:
        print('%s: %i' % (root, cnt))
