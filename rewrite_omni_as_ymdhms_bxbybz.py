import pdb
import datetime as dt
in_fname = 'imf_data.txt'

out_fname = 'imf_data2.txt'

with open(in_fname, 'r') as f:
    txt = f.readlines()

outtxt = []
for line in txt:
    vals = line.split()
    time = dt.datetime.strptime(' '.join(vals[:3]), '%Y %j %H')
    outtxt.append('%s %s %s %s \n' % (time.strftime('%Y %-m %-d %-H %-M %-S'), *vals[3:]))
with open(out_fname, 'w') as f:
    f.writelines(outtxt)
print('Wrote to %s' % out_fname)

