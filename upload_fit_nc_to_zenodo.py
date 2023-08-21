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
import requests
import datetime as dt
from dateutil.relativedelta import relativedelta
import helper
import json
import glob
import time
    
__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2023, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

# Zenodo upload metadata
wikerORCID = '0000-0003-4707-5539'
chartierORCID = '0000-0002-4215-031X'
aplAffiliation = 'JHU/APL'
keywords = 'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, netcdf, aeronomy, cedar, gem, radar, OTHR'

USE_SANDBOX = False

def main(date):

    startTime = time.time()
    emailSubject = '"Starting Zenodo Upload"'
    emailBody = '"Starting to upload {0} netCDF files to Zenodo"'.format(date.strftime('%Y-%m'))
    helper.send_email(emailSubject, emailBody)

    upload_to_zenodo(USE_SANDBOX, date)

    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"Finished Zenodo Upload"'
    emailBody = '"Finished uploading {0} netCDF files\nTotal time: {1}"'.format(date.strftime('%Y-%m'), totalTime)
    helper.send_email(emailSubject, emailBody)
    

def upload_to_zenodo(sandbox, date):
  
    accessToken = helper.ZENODO_SANDBOX_TOKEN if sandbox else helper.ZENODO_TOKEN
    depositURL = helper.SANDBOX_DEPOSIT_URL if sandbox else helper.DEPOSIT_URL

    uploadDir = date.strftime(helper.NETCDF_DIR_FMT)
    
    if date.year > helper.LATEST_PUBLIC_DATA:
        fileList = glob.glob(os.path.join(uploadDir, '*wal**.nc'))
    else:
        fileList = glob.glob(os.path.join(uploadDir, '*.nc'))

    if len(fileList) == 0:
        print('No files to upload in {0}'.format(uploadDir))
        return 1
    else:
        print('Uploading {0} {1} files to Zenodo'.format(len(fileList), date.strftime('%Y-%m')))
    
    headers = {"Content-Type": "application/json"}
    params = {'access_token': accessToken}
    r = requests.post(depositURL,
                   params=params,
                   json={},
                   headers=headers)

    bucket_url = r.json()["links"]["bucket"]
    deposition_id = r.json()['id']
    helper.check_remaining_zenodo_requests(r)

    # The target URL is a combination of the bucket link with the desired filename
    for file in fileList:
        filename = file.split('/')[-1]
        with open(file, "rb") as fp:
            r = requests.put(
                "%s/%s" % (bucket_url, filename),
                data=fp,
                params=params,
            )
            helper.check_remaining_zenodo_requests(r)
    
    if date.year > helper.LATEST_PUBLIC_DATA:
        data = {
            'metadata': {
                'title': 'Wallops SuperDARN data in netCDF format ({0})'.format(date.strftime('%Y-%b')),
                'upload_type': 'dataset',
                'description': '<p>{0} Wallops SuperDARN radar data in netCDF format. These files were produced using versions 2.5 and 3.0 of the public FitACF algorithm, using the AACGM v2 coordinate system. Cite this dataset if using our data in a publication.</p><p>The RST is available here:&nbsp;https://github.com/SuperDARN/rst</p><p>The research enabled by SuperDARN is due to the efforts of teams of scientists and engineers working in many countries to build and operate radars, process data and provide access, develop and improve data products, and assist users in interpretation. Users of SuperDARN data and data products are asked to acknowledge this support in presentations and publications. A brief statement on how to acknowledge use of SuperDARN data is provided below.<p>Users are also asked to consult with a SuperDARN PI prior to submission of work intended for publication. A listing of radars and PIs with contact information can be found here: (<a href="http://vt.superdarn.org/tiki-index.php?page=Radar+Overview">SuperDARN Radar Overview</a>)</p><p><strong>Recommended form of acknowledgement for the use of SuperDARN data:</strong></p><p>‘The authors acknowledge the use of SuperDARN data. SuperDARN is a collection of radars funded by national scientific funding agencies of Australia, Canada, China, France, Italy, Japan, Norway, South Africa, United Kingdom and the United States of America.’</p>'.format(date.strftime('%Y-%b')),
                'creators': [
                    {
                        'orcid': chartierORCID, 
                        'affiliation': aplAffiliation, 
                        'name': 'Chartier, Alex T.'
                    }, 
                    {
                        'orcid': wikerORCID,
                        'affiliation': aplAffiliation,
                        'name': 'Wiker, Jordan R.'
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
                'version': '1.0',
            }
        }
    else:
        data = {
            'metadata': {
                'title': 'SuperDARN data in netCDF format ({0})'.format(date.strftime('%Y-%b')),
                'upload_type': 'dataset',
                'description': '<p>{0} SuperDARN radar data in netCDF format. These files were produced using versions 2.5 and 3.0 of the public FitACF algorithm, using the AACGM v2 coordinate system. Cite this dataset if using our data in a publication.</p><p>The RST is available here:&nbsp;https://github.com/SuperDARN/rst</p><p>The research enabled by SuperDARN is due to the efforts of teams of scientists and engineers working in many countries to build and operate radars, process data and provide access, develop and improve data products, and assist users in interpretation. Users of SuperDARN data and data products are asked to acknowledge this support in presentations and publications. A brief statement on how to acknowledge use of SuperDARN data is provided below.<p>Users are also asked to consult with a SuperDARN PI prior to submission of work intended for publication. A listing of radars and PIs with contact information can be found here: (<a href="http://vt.superdarn.org/tiki-index.php?page=Radar+Overview">SuperDARN Radar Overview</a>)</p><p><strong>Recommended form of acknowledgement for the use of SuperDARN data:</strong></p><p>‘The authors acknowledge the use of SuperDARN data. SuperDARN is a collection of radars funded by national scientific funding agencies of Australia, Canada, China, France, Italy, Japan, Norway, South Africa, United Kingdom and the United States of America.’</p>'.format(date.strftime('%Y-%b')),
                'creators': [
                    {
                        'orcid': chartierORCID, 
                        'affiliation': aplAffiliation, 
                        'name': 'Chartier, Alex T.'
                    }, 
                    {
                        'orcid': wikerORCID,
                        'affiliation': aplAffiliation,
                        'name': 'Wiker, Jordan R.'
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
                'related_identifiers' : [{'relation': 'isSourceOf', 'identifier':helper.getDOI(date.year),'resource_type': 'dataset'}],
                'version': '1.0',
            }
        }

    r = requests.put(depositURL + '/%s' % deposition_id,
    params={'access_token': accessToken}, data=json.dumps(data), headers=headers)
    
    helper.check_remaining_zenodo_requests(r)


if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 2:
        # If no date was passed in, process the previous month
        today = dt.datetime.now()
        date = today - relativedelta(months=1)
    else:
        date = args[1]
    
    main(date)

