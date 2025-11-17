# Makefile for meteorproc
# =======================
# Author: R.J.Barnes
#
#
include $(MAKECFG).$(SYSTEM)

INCLUDE=-I$(IPATH)/base -I$(IPATH)/general -I$(IPATH)/superdarn
OBJS = meteorproc.o math.o nrutil.o
SRC=meteorproc.c math.c nrutil.c nrutil.h math.h meteor.h
DSTPATH = $(BINPATH)
OUTPUT = meteorproc
LIBS=-lcfit.1 -lrscan.1 -ldmap.1 -liaacgm.1 -ligrf.1 -lrpos.1 -lradar.1 -lrtime.1 -lopt.1 -lrcnv.1 
SLIB=-lm -lz
include $(MAKEBIN).$(SYSTEM)






