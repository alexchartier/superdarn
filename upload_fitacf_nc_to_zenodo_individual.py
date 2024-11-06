import sys
import os
import requests
from datetime import datetime
import json
import glob
import time

import helper

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

def main(date_string, use_sandbox=True):
    date = datetime.strptime(date_string, '%Y%m')
    print(f'Starting to upload {date.strftime("%Y-%m")} fitACF files in netCDF format to Zenodo')
    startTime = time.time()

    upload_to_zenodo(date, use_sandbox)

    totalTime = helper.get_time_string(time.time() - startTime)
    emailSubject = '"Finished Zenodo Upload"'
    emailBody = '"Finished uploading {0} fitACF nc files\nTotal time: {1}"'.format(date.strftime('%Y-%m'), totalTime)
    # helper.send_email(emailSubject, emailBody)
    
def upload_to_zenodo(date, sandbox):
    accessToken = helper.ZENODO_SANDBOX_TOKEN if sandbox else helper.ZENODO_TOKEN
    depositURL = helper.SANDBOX_DEPOSIT_URL if sandbox else helper.DEPOSIT_URL
    refererURL = 'https://sandbox.zenodo.org' if sandbox else 'https://zenodo.org'
    upload_dir = date.strftime(helper.FIT_NC_DIR_FMT)
    
    if date.year > helper.LATEST_PUBLIC_DATA:
        file_list = glob.glob(os.path.join(upload_dir, '*wal*.nc'))
    else:
        file_list = glob.glob(os.path.join(upload_dir, '*.nc'))

    if len(file_list) == 0:
        print('No files to upload in {0}'.format(upload_dir))
        return 1
    else:
        file_list.sort()
        print(f'Uploading {len(file_list)} {date.strftime("%Y-%m")} files to Zenodo')
    
    headers = {
        "Content-Type": "application/json",
        "Referer": refererURL
    }
    params = {'access_token': accessToken}
    r = requests.post(depositURL, params=params, json={}, headers=headers)

    if r.status_code != 201:
        print(f'Error creating deposition\n')
        check_response_status(r.status_code)
        return 1

    bucket_url = r.json().get("links", {}).get("bucket")
    if not bucket_url:
        print(f'Error: no bucket link in response: {r.json()}')
        return 1
    
    deposition_id = r.json()['id']
    helper.check_remaining_zenodo_requests(r)

    # The target URL is a combination of the bucket link with the desired filename
    for file in file_list:
        filename = os.path.basename(file)
        with open(file, "rb") as fp:
            r = requests.put(
                f"{bucket_url}/{filename}",
                data=fp,
                params=params,
            )
            if r.status_code != 201:
                print(f'Error uploading file {filename}: {r.status_code}, {r.json()}')
                return 1
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
                    {'identifier':'spacephysics'},
                    {'identifier':'superdarn'}
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
                    {'identifier':'spacephysics'},
                    {'identifier':'superdarn'}
                ],
                'related_identifiers' : [{'relation': 'isSourceOf', 'identifier':helper.getDOI(date.year),'resource_type': 'dataset'}],
                'version': '1.0',
            }
        }

    r = requests.put(depositURL + '/%s' % deposition_id, params={'access_token': accessToken}, data=json.dumps(data), headers=headers)
    
    if not check_response_status(r):
        return 1

    helper.check_remaining_zenodo_requests(r)
    print('Upload to Zenodo completed successfully.')

# def sort_files_on_zenodo(deposit_id, access_token, file_ids):
#     url = f'https://zenodo.org/api/deposit/depositions/{deposit_id}/files?access_token={access_token}'
#     headers = {"Content-Type": "application/json"}
#     data = [{'id': file_id} for file_id in file_ids]
#     r = requests.put(url, data=json.dumps(data), headers=headers)
    
#     if r.status_code == 200:
#         print("Files sorted successfully")
#     else:
#         print(f'Error sorting files: {r.status_code}, {r.json()}')
#         return 1

def check_response_status(r):
    status_codes = {
        200: ("OK", "Request succeeded. Response included. Usually sent for GET/PUT/PATCH requests."),
        201: ("Created", "Request succeeded. Response included. Usually sent for POST requests."),
        202: ("Accepted", "Request succeeded. Response included. Usually sent for POST requests, where background processing is needed to fulfill the request."),
        204: ("No Content", "Request succeeded. No response included. Usually sent for DELETE requests."),
        400: ("Bad Request", "Request failed. Error response included."),
        401: ("Unauthorized", "Request failed, due to an invalid access token. Error response included."),
        403: ("Forbidden", "Request failed, due to missing authorization (e.g. deleting an already submitted upload or missing scopes for your access token). Error response included."),
        404: ("Not Found", "Request failed, due to the resource not being found. Error response included."),
        405: ("Method Not Allowed", "Request failed, due to unsupported HTTP method. Error response included."),
        409: ("Conflict", "Request failed, due to the current state of the resource (e.g. edit a deposition which is not fully integrated). Error response included."),
        415: ("Unsupported Media Type", "Request failed, due to missing or invalid request header Content-Type. Error response included."),
        429: ("Too Many Requests", "Request failed, due to rate limiting. Error response included."),
        500: ("Internal Server Error", "Request failed, due to an internal server error. Error response NOT included. Don’t worry, Zenodo admins have been notified and will be dealing with the problem ASAP.")
    }

    if r.status_code in [200, 201, 202, 204]:
        return True
    
    if r.status_code in status_codes:
        name, description = status_codes[r.status_code]
        print(f"Error\nStatus Code: {r.status_code} - {name}: {description}")
    else:
        print(f"Error\nStatus Code: {r.status_code} - Unknown status code")

    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 upload_fitacf_nc_to_zenodo.py <date> [<use_sandbox>]")
        sys.exit(1)

    # Extract the date argument in 'YYYYMM' format
    date_string = sys.argv[1]

    # Check if the date argument is in the correct format
    if not date_string.isdigit() or len(date_string) != 6:
        print("Date argument must be in 'YYYYMM' format.")
        sys.exit(1)

    use_sandbox = sys.argv[2].lower() == 'true' if len(sys.argv) > 2 else True

    main(date_string, use_sandbox)
