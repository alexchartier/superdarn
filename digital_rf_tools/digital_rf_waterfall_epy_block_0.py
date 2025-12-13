"""
Embedded Python Blocks:

Digital RF source for the rooftop capture. Outputs complex64 samples scaled to +/-1.
"""

import os
import site
import numpy as np
from gnuradio import gr
site.addsitedir('/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages')
import digital_rf as drf

class blk(gr.sync_block):
    def __init__(self, dataset_root='/Users/chartat1/data/hf_data/itsi_rooftop/single_channelroofafternewradio', channel='cha', block_size=32768):
        gr.sync_block.__init__(
            self,
            name='digital_rf_source',
            in_sig=[],
            out_sig=[np.complex64],
        )
        self.dataset_root = os.path.expanduser(dataset_root)
        self.channel = channel
        self.block_size = int(block_size)
        self.reader = drf.DigitalRFReader(self.dataset_root)
        self.bounds = self.reader.get_bounds(self.channel)
        self.next_sample = self.bounds[0]

    def work(self, input_items, output_items):
        out = output_items[0]
        n_req = min(len(out), self.block_size)

        if self.next_sample > self.bounds[1]:
            return -1

        end = min(self.next_sample + n_req - 1, self.bounds[1])
        data_dict = self.reader.read(self.next_sample, end, self.channel)
        produced = 0

        if data_dict:
            block = next(iter(data_dict.values()))
            r = block['r'][:, 0].astype(np.float32)
            i = block['i'][:, 0].astype(np.float32)
            c = (r + 1j * i) * (1.0 / 32768.0)
            produced = len(c)
            out[:produced] = c

        if produced < n_req:
            out[produced:n_req] = 0

        self.next_sample += n_req
        return n_req
