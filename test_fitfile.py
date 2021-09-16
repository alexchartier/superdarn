import pydarn
in_fname = 'data/fitacf/2014/04/20140423.kod.c.fit'
SDarn_read = pydarn.SuperDARNRead(in_fname)
data = SDarn_read.read_fitacf()
print('%s \n' % in_fname)

for fld in ['elv', 'elv_high']:
    print(fld)
    for rec in data:
        try:
            print(["{0:0.2f}".format(i) for i in rec[fld]])
        except:
            None
