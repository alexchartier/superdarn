import sys
import os
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import glob
import time

import helper

# Zenodo upload metadata
wikerORCID = '0000-0003-4707-5539'
chartierORCID = '0000-0002-4215-031X'
aplAffiliation = 'JHU/APL'
keywords = 'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, netcdf, aeronomy, cedar, gem, radar, OTHR'

def main(start_date_string, end_date_string, sandbox=True):
    start_date = datetime.strptime(start_date_string, '%Y%m')
    end_date = datetime.strptime(end_date_string, '%Y%m')

    accessToken = helper.ZENODO_SANDBOX_TOKEN if sandbox else helper.ZENODO_TOKEN
    depositURL = helper.SANDBOX_DEPOSIT_URL if sandbox else helper.DEPOSIT_URL
    refererURL = 'https://sandbox.zenodo.org' if sandbox else 'https://zenodo.org'

    date = start_date
    while date <= end_date:
        monthString = date.strftime('%Y-%b')
        deposit_id = get_deposit_id(monthString, accessToken, depositURL, refererURL)
        print(f"Found deposit ID: {deposit_id} for {monthString}")
        create_new_version(date, deposit_id, accessToken, depositURL, refererURL)
        date += relativedelta(months=1)
    

    # upload_to_zenodo(start_date, end_date, use_sandbox)

    # totalTime = helper.get_time_string(time.time() - startTime)
    # emailSubject = '"Finished Zenodo Upload"'
    # emailBody = '"Finished uploading fitACF nc files\nTotal time: {0}"'.format(totalTime)
    # helper.send_email(emailSubject, emailBody)
    

def get_deposit_id(monthString, accessToken, depositURL, refererURL):
    print(f"{time.strftime('%Y-%m-%d %H:%M')}: Getting Zenodo fitACF netCDF data for {monthString}")

    response = requests.get('https://zenodo.org/api/records',
                            params={'q': f'"SuperDARN data in netCDF format ({monthString})"',
                                    'access_token': accessToken})

    if response.json()["hits"]["hits"]:
        deposit_id = response.json()["hits"]["hits"][0]["id"]
        return deposit_id
    else:
        print(f"No deposit found for {monthString}")

    
def create_new_version(date, deposit_id, accessToken, depositURL, refererURL):
    monthString = date.strftime('%Y-%b')
    uploadDir = date.strftime(helper.FIT_NC_DIR_FMT)
    new_version_response = requests.post(
        f'{depositURL}/{deposit_id}/actions/newversion',
        params={'access_token': accessToken}
    )

    if new_version_response.status_code != 201:
        print(f"Error creating new version for deposit ID {deposit_id}\n")
        check_response_status(new_version_response)
        return

    latest_draft = new_version_response.json()["links"]["latest_draft"]
    new_deposit_id = latest_draft.split('/')[-1]

    print(f"New version created with deposit ID: {new_deposit_id} for {monthString}")  
    breakpoint()

    if new_version_response.json()["files"]:
        files = new_version_response.json()["files"]
        for file in files: 
            file_link = file["links"]["self"]      
            r = requests.delete(file_link, params={'access_token': accessToken})  
            if r.status_code != 204:
                print(f'Error deleting {file["filename"]}: {r.status_code}, {r.json()}')
                return 1
            helper.check_remaining_zenodo_requests(r)

    breakpoint()
    
    if date.year > helper.LATEST_PUBLIC_DATA:
        file_list = glob.glob(os.path.join(uploadDir, '*wal*.nc'))
    else:
        file_list = glob.glob(os.path.join(uploadDir, '*.nc'))

    if len(file_list) == 0:
        print('No files to upload in {0}'.format(uploadDir))
        return 1
    else:
        file_list.sort()
        print(f'Uploading {len(file_list)} {date.strftime("%Y-%m")} files to Zenodo')
    
    headers = {
        "Content-Type": "application/json",
        "Referer": refererURL
    }
    params = {'access_token': accessToken}
    
    bucket_url = new_version_response.json().get("links", {}).get("bucket")
    if not bucket_url:
        print(f'Error: no bucket link in response: {r.json()}')
        return 1
    
    helper.check_remaining_zenodo_requests(new_version_response)

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

    breakpoint()
    
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
                'version': '2.0',
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
                'version': '2.0',
            }
        }

    # r = requests.put(depositURL + '/%s' % deposit_id, params={'access_token': accessToken}, data=json.dumps(data), headers=headers)
    
    # if not check_response_status(r):
    #     return 1

    helper.check_remaining_zenodo_requests(r)
    print('Upload to Zenodo completed successfully.')

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
    if len(sys.argv) < 3:
        print("Usage: python3 upload_new_version_to_zenodo.py <start_date> <end_date> [<use_sandbox>]")
        sys.exit(1)

    # Extract the date arguments in 'YYYYMM' format
    start_date_string = sys.argv[1]
    end_date_string = sys.argv[2]

    # Check if the date arguments are in the correct format
    if not start_date_string.isdigit() or len(start_date_string) != 6:
        print("Start date argument must be in 'YYYYMM' format.")
        sys.exit(1)
    if not end_date_string.isdigit() or len(end_date_string) != 6:
        print("End date argument must be in 'YYYYMM' format.")
        sys.exit(1)

    use_sandbox = sys.argv[3].lower() == 'true' if len(sys.argv) > 3 else True

    main(start_date_string, end_date_string, use_sandbox)
