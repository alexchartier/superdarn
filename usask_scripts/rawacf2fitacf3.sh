#!/bin/bash
# copyright (C) SuperDARN Canada, University of Saskatchewan 
# Non-Licensed Script:
# This script is under SuperDARN Canada's use-only. No distrubuting, copying or modfying is 
# allowed for this script unless one has obtained approval from a SuperDARN Canada member. 

# This script converts a single rawacf file to fitacf 3.0 
# called by: convert_rawacf2fitacf.sh

# input parameters
# YYYYMMDD.HHMM.SS.<3 letter radar abrv.>.<channel>
FILENAME=$1 
RAWDIR=$2
FITACFDIR=$3 
TMPFITACFDIR=$4
TMPRAWDIR=$5
LOG=$6

LOGFILE=${LOG}/${FILENAME}.fitacf.3.0.log

# copy and unzip rawacf file
cp ${RAWDIR}/${FILENAME}.rawacf.bz2 ${TMPRAWDIR}/
bzip2 -d ${TMPRAWDIR}/${FILENAME}.rawacf.bz2 2>${LOGFILE}
return_value=$?
if [ ${return_value} -ne 0 ]
then
	echo "Error: could not unzip ${FILENAME}.rawacf.bz2" >> ${LOGFILE}
	exit -1 
fi

# run make_fit
echo "make_fit -fitacf-version 3.0 ${TMPRAWDIR}/${FILENAME}.rawacf > ${TMPFITACFDIR}/${FILENAME}.fitacf" 
make_fit -fitacf-version 3.0 ${TMPRAWDIR}/${FILENAME}.rawacf > ${TMPFITACFDIR}/${FILENAME}.fitacf 
returnvalue=$?
# Check if make_fit succeeded, if not then log it and remove it
if [ ${returnvalue} -ne 0 ]
then
    echo "Error: make_fit returned ${returnvalue} on ${TMPRAWDIR}/${FILENAME}.rawacf" >> ${LOGFILE}
    rm -v  ${TMPFITACFDIR}/${FILENAME}.fitacf
    rm -v  ${TMPRAWDIR}/${FILENAME}.rawacf
    exit -1 
# Check if make_fit succeeded, if not then log it, remove it, and email the peeps 
elif [ ! -s ${TMPFITACFDIR}/${FILENAME}.fitacf ] 
then
    "Error: make_fit generated a empty fitacf file ${FILENAME}.fitacf" >> ${LOGFILE}
    rm -v ${TMPFITACFDIR}/${FILENAME}.fitacf 
    rm -v  ${TMPRAWDIR}/${FILENAME}.rawacf
    exit -1 
fi
# bzip and check for errors on the file
bzip2 ${TMPFITACFDIR}/${FILENAME}.fitacf 2>${LOGFILE}
return_value=$?
if [ ${return_value} -ne 0 ]
then
	echo "Error: could no zip ${FILENAME}.fitacf" >> ${LOGFILE}
    rm -v ${TMPFITACFDIR}/${FILENAME}.fitacf	
	exit -1 
fi

bzip2 -t ${TMPFITACFDIR}/${FILENAME}.fitacf.bz2 2>${LOGFILE}
return_value=$?
if [ ${return_value} -ne 0 ]
then
	echo "Error: zip was not successful ${FILENAME}.fitacf" >> ${LOGFILE}
    rm -v ${TMPFITACFDIR}/${FILENAME}.fitacf.bz2	
	exit -1 
fi

# check file is correct processed 
python3 pydarnio_checker.py ${TMPFITACFDIR}/${FILENAME}.fitacf.bz2 2>${LOGFILE}
return_value=$?
if [[ ${return_value} -ne 0 ]];
then
    echo "Error: ${FILENAME}.fitacf did not pass pydarn checking test" >> ${LOGFILE}
    rm -v ${TMPFITACFDIR}/${FILENAME}.fitacf.bz2	
    exit -1
fi 

if [ ! -s ${LOGFILE} ] 
then
    rm -v ${LOGFILE}
fi

# change ownership, permissions 
exit 0 
