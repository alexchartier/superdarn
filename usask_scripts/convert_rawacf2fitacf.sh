#!/bin/bash
#(C) copyrights of SuperDARN Canada, University of Saskatchewan 
# Author: Marina Schmidt 
# Non-Licensed Script:
# This script is under SuperDARN Canada's use-only. No distrubuting, copying or modfying is 
# allowed for this script unless one has obtained approval from a SuperDARN Canada member. 
# 
# Description: This file setups parallel jobs to process rawacf files to:
# - Fitacf 2.5 
# - Fitacf 3.0
# - Fitacf 3.0 + Despecking
# called by: workflow.sh

# Input parameters
YEAR=$1
month=$2
LOG=$3

# directories for RAWACF and FITACF folders
RAWDIR=/home/mschmidt/projects/rpp-kam136/sdarn/chroot/sddata/raw/${YEAR}/${month}/
FITACF3DIR=/home/mschmidt/projects/rpp-kam136/sdarn/local_data/fitacf_30/${YEAR}/${month}/

# TEMP folders to work in
TMPFITACF3DIR=/home/mschmidt/scratch/tmp_fitacf3/${YEAR}/${month}/

# create temp dirs
mkdir -p ${TMPFITACF3DIR}/raw
# ensure fitacf dirs exist
mkdir -p ${FITACF3DIR}

# this line and the other ones look at all rawacf files and compare their dates-times-radar name to the fitacf files and see which ones are missing, if missing generate it. This prevents regenerating and wasting 
# time and resources on this. 
#TODO replace need_to_generate to hash file check :)
# can replace with grabbing form globus and getting the list of files 
need_to_generate=$(sort <(find ${RAWDIR}/*rawacf.bz2 -type f -name *rawacf.bz2 -exec bash -c 'basename "${0%.*.*}"' {} \; | sort) <(find ${FITACF3DIR}/ -type f -exec bash -c 'basename "${0%.*.*}"' {} \; | sort) | uniq -u)

# run fitacf 2.5
# nproc - number of processes you have availble this is a bash command
parallel -j$(nproc) rawacf2fitacf3 {} ${RAWDIR} ${FITACF3DIR} ${TMPFITACF3DIR} ${TMPFITACF3DIR}/raw ${LOG} ::: ${need_to_generate}

mv -v ${TMPFITACF3DIR}/*fitacf.bz2 ${FITACF3DIR}/

# remove temp files
rm -rf ${TMPFITACF3DIR}

exit 0
