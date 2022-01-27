"""
upload_nc_to_zenodo.py

Upload SuperDARN netCDF files to Zenodo

Terms:
    Zenodo - https://zenodo.org
    .nc  - netCDF output file (self-describing platform-independent file suitable 
           for sharing with users outside the community)
            Daily, one per hemisphere
"""  
import sys, os
# TODO: Remove this once requests is installed for python3
# sys.path.append('/usr/lib/python2.7/site-packages/')
import requests
import datetime as dt
from dateutil.relativedelta import relativedelta
import helper
import json
import glob
    
__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2022, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

# Zenodo upload metadata
wikerORCID = '0000-0003-4707-5539'
chartierORCID = '0000-0002-4215-031X'
aplAffiliation = 'JHU/APL'
keywords = 'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, netcdf, aeronomy, cedar, gem, radar, OTHR'

DEPOSIT_URL = 'https://zenodo.org/api/deposit/depositions'
SANDBOX_DEPOSIT_URL = 'https://sandbox.zenodo.org/api/deposit/depositions'
SANDBOX = False

ZENODO_TOKEN = 'RT4wr3kTsZkEgwWC4r99VTytmGqzULUzloRqn8nVirg2e5nGBYxw4Ohy5FUf'
ZENODO_SANDBOX_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'

def main(date):
    startTime = time.time()
    emailSubject = '"Starting Zenodo Upload"'
    emailBody = '"Starting to upload {0} netCDF files to Zenodo"'.format(date.strftime('%Y-%m'))
    helper.send_email(emailSubject, emailBody)

    upload_to_zenodo(SANDBOX, date)

    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"Finished Zenodo Upload"'
    emailBody = '"Finished uploading {0} netCDF files\nTotal time: {1}"'.format(date.strftime('%Y-%m'), totalTime)
    helper.send_email(emailSubject, emailBody)
    

def upload_to_zenodo(sandbox, date):
  
    accessToken = ZENODO_SANDBOX_TOKEN if sandbox else ZENODO_TOKEN
    depositURL = SANDBOX_DEPOSIT_URL if sandbox else DEPOSIT_URL

    uploadDir = date.strftime(helper.NETCDF_DIR_FMT)
    fileList = glob.glob(os.path.join(uploadDir, '*.nc'))

    headers = {"Content-Type": "application/json"}

    params = {'access_token': accessToken}
    r = requests.post(depositURL,
                   params=params,
                   json={},
                   # Headers are not necessary here since "requests" automatically
                   # adds "Content-Type: application/json", because we're using
                   # the "json=" keyword argument
                   # headers=headers,
                   headers=headers)

    bucket_url = r.json()["links"]["bucket"]
    deposition_id = r.json()['id']

    # The target URL is a combination of the bucket link with the desired filename
    # seperated by a slash.
    for file in fileList:
        filename = file.split('/')[-1]
        with open(file, "rb") as fp:
            r = requests.put(
                "%s/%s" % (bucket_url, filename),
                data=fp,
                params=params,
            )
    
    # data = {
    #     'metadata': {
    #         'title': 'My first upload',
    #         'upload_type': 'dataset',
    #         'description': 'This is my first upload',
    #         'creators': [{'name': 'Wiker, Jordan','affiliation': 'JHUAPL'}],
    #         'communities': [{"id": "superdarn"}]
    #         }
    #     }

    # r = requests.put('https://sandbox.zenodo.org/api/deposit/depositions/%s' % deposition_id, params={'access_token': accessToken}, data=json.dumps(data), headers=headers)
    
    
    data = {
        'metadata': {
            'title': 'SuperDARN data in netCDF format ({0})'.format(date.strftime('%Y-%m')),
            'upload_type': 'dataset',
            'description': '<p>{0} SuperDARN radar data in netCDF format. These files were produced using versions 2.5 and 3.0 of the public FitACF algorithm, using the AACGM v2 coordinate system. Cite this dataset if using our data in a publication.</p><p>The RST is available here:&nbsp;https://github.com/SuperDARN/rst</p>'.format(date.strftime('%Y-%m')),
            'creators': [
                {
                    'orcid': chartierORCID, 
                    'affiliation': aplAffiliation, 
                    'name': 'Chartier, Alex T.'
                }, 
                {
                    'orcid': chartierORCID,
                    'affiliation': aplAffiliation,
                    'name': 'Wiker, Jordan R.'
                },
                {
                  "affiliation": aplAffiliation, 
                  "name": "Barnes, Robin J."
                }, 
                {
                  "affiliation": "STR", 
                  "name": "Miller, Ethan S."
                }, 
                {
                  "affiliation": "NOAA", 
                  "name": "Talaat, Elsayed R."
                }, 
                {
                  "affiliation": "Virginia Tech", 
                  "name": "Ruohoniemi, J. Mike"
                }, 
                {
                  "affiliation": "Virginia Tech", 
                  "name": "Greenwald, Raymond A."
                }
            ],
            'keywords': [
                'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, cfit, aeronomy, cedar, gem, radar'
            ],
            'communities': [
                {
                    'identifier': 'spacephysics'
                }, 
                {
                    'identifier': 'superdarn'
                }
            ],
            'version': '1.0'
        }
    }

    r = requests.put(depositURL + '/%s' % deposition_id,
    params={'access_token': accessToken}, data=json.dumps(data), headers=headers)


if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 2:
        # If no date was passed in, process the previous month
        today = dt.datetime.now()
        date = today - relativedelta(months=1)
    else:
        date = args[1]
    
    main(date)

