"""
upload_fitacf_nc_to_zenodo.py

Upload SuperDARN fitACF files to Zenodo in netCDF format

Terms:
    Zenodo - https://zenodo.org
    .nc  - netCDF output file (self-describing platform-independent file suitable 
           for sharing with users outside the community)
            Daily, one per hemisphere
"""  
import sys, os
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import helper
import json
import glob
import time
from calendar import monthrange
    
__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2024, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

# Zenodo upload metadata
wikerORCID = '0000-0003-4707-5539'
chartierORCID = '0000-0002-4215-031X'
aplAffiliation = 'JHU/APL'
keywords = 'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, netcdf, aeronomy, cedar, gem, radar, OTHR'

# TODO: Switch to false
USE_SANDBOX = True

def main(date_string):

    date = datetime.strptime(date_string, '%Y%m%d')
    print(f'Starting to upload {date.strftime("%Y-%m")} netCDF files to Zenodo')
    startTime = time.time()

    directory = "/project/superdarn/data/netcdf"
    year = 2022  # Replace with the desired year

    for month in range(1, 13):
        days_in_month = monthrange(year, month)[1]
        
        for day in range(1, days_in_month + 1):
            pattern = f"{year}{month:02d}{day:02d}"
            files_found = [f for f in os.listdir(f"{directory}/{year}/{month:02d}") if f.startswith(pattern)]

            if not files_found:
                print(f"No files found for {pattern}")
            else:
                print(f"Files found for {pattern}:")
                for file in files_found:
                    print(file)

    if has_files_for_each_day(date):
        upload_to_zenodo(USE_SANDBOX, date)
    else:
        print(f'There\'s at least one day without any files in {date.strftime(helper.FIT_NC_DIR_FMT)}')

    totalTime = helper.getTimeString(time.time() - startTime)
    emailSubject = '"Finished Zenodo Upload"'
    emailBody = '"Finished uploading {0} netCDF files\nTotal time: {1}"'.format(date.strftime('%Y-%m'), totalTime)
    helper.send_email(emailSubject, emailBody)
    
    
def has_files_for_each_day(date):
    uploadDir = date.strftime(helper.FIT_NC_DIR_FMT)

    year, month = date.year, date.month
    days_in_month = monthrange(year, month)[1]

    for day in range(1, days_in_month + 1):
        pattern = f"{year}{month:02d}{day:02d}"
        files_found = [f for f in os.listdir(f"{uploadDir}/{year}/{month:02d}") if f.startswith(pattern)]

        if not files_found:
            return False

    return True


def upload_to_zenodo(sandbox, date):
  
    accessToken = helper.ZENODO_SANDBOX_TOKEN if sandbox else helper.ZENODO_TOKEN
    depositURL = helper.SANDBOX_DEPOSIT_URL if sandbox else helper.DEPOSIT_URL

    uploadDir = date.strftime(helper.FIT_NC_DIR_FMT)
    
    if date.year > helper.LATEST_PUBLIC_DATA:
        fileList = glob.glob(os.path.join(uploadDir, '*wal*.nc'))
    else:
        fileList = glob.glob(os.path.join(uploadDir, '*.nc'))

    if len(fileList) == 0:
        print('No files to upload in {0}'.format(uploadDir))
        return 1
    else:
        print(f'Uploading {len(fileList)} {date.strftime("%Y-%m")} files to Zenodo')
    
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
    if len(sys.argv) < 2:
        print("Usage: python3 upload_fitacf_nc_to_zenodo.py YYYYMMDD")
        sys.exit(1)

    # Extract the day argument in 'YYYYMMDD' format
    date_string = sys.argv[1]

    # Check if the day argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 8:
        print("Date argument must be in 'YYYYMMDD' format.")
        sys.exit(1)

    main(date_string)

