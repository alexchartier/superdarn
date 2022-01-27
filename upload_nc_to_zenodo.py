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
import argparse
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

SANDBOX = True

# TODO: Add non-sandbox Zenodo token, and confirm deposit:write is enabled
ZENODO_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'
ZENODO_SANDBOX_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'

def main(date):
    accessToken = ZENODO_SANDBOX_TOKEN if SANDBOX else ZENODO_TOKEN
    uploadDir = date.strftime(helper.NETCDF_DIR_FMT)
    upload_to_zenodo(accessToken, uploadDir)
    

def upload_to_zenodo(accessToken, uploadDir):
    # TODO: Remove this dir
    uploadDir = '/Users/wikerjr1/Desktop/zenodotest/'
    fileList = glob.glob(os.path.join(uploadDir, '*.nc'))

    headers = {"Content-Type": "application/json"}

    params = {'access_token': accessToken}
    r = requests.post('https://sandbox.zenodo.org/api/deposit/depositions',
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
            'title': 'Test Upload',
            'upload_type': 'dataset',
            'description': 'Test upload',
            'creators': [
                {
                    'orcid': chartierORCID, 
                    'affiliation': aplAffiliation, 
                    'name': 'Chartier, Alex T.'
                }, 
                {
                    'orcid': chartierORCID,
                    'affiliation': aplAffiliation,
                    'name': 'Wiker, Jordan'
                }
            ],
            'keywords': [
                'SuperDARN, ionosphere, magnetosphere, convection, rst, fitacf, cfit, aeronomy, cedar, gem, radar'
            ],
            "communities": [
                {
                    "identifier": "spacephysics"
                } 
                # {
                #     "id": "superdarn"
                # }
            ], 
        }
    }

    r = requests.put('https://sandbox.zenodo.org/api/deposit/depositions/%s' % deposition_id,
    params={'access_token': accessToken}, data=json.dumps(data), headers=headers)


# def _build_arg_parser(Parser, *args):
#     scriptname = os.path.basename(sys.argv[0])

#     formatter = argparse.RawDescriptionHelpFormatter(scriptname)
#     width = formatter._width

#     title = "zenodo_uploader"
#     copyright = "Copyright (c) 2022 JHU/APL"
#     shortdesc = "Upload SuperDARN netCDF files to Zenodo"
#     desc = "\n".join(
#         (
#             "*" * width,
#             "*{0:^{1}}*".format(title, width - 2),
#             "*{0:^{1}}*".format(copyright, width - 2),
#             "*{0:^{1}}*".format("", width - 2),
#             "*{0:^{1}}*".format(shortdesc, width - 2),
#             "*" * width,
#         )
#     )

#     usage = (
#         "%s [sandbox] [-d YYYY-m-d]" % scriptname
#     )

#     # parse options
#     parser = Parser(
#         description=desc,
#         usage=usage,
#         prefix_chars="-+",
#         formatter_class=argparse.RawDescriptionHelpFormatter,
#     )

#     parser.add_argument(
#         "--sandbox",
#         action="store_true",
#         help="""Upload to the APL Sandbox Zenodo account""",
#     )

#     parser.add_argument(
#         "-d",
#         "--date",
#         dest="date",
#         default=None,
#         help="""Month to upload - format: 'YYYY-m-d'""",
#     )

#     return parser


if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 2:
        # If no date was passed in, process the previous month
        today = dt.datetime.now()
        date = today - relativedelta(months=1)
    else:
        date = args[1]
    
    main(date)

# if __name__ == '__main__':
#     parser = _build_arg_parser(argparse.ArgumentParser)
#     args = parser.parse_args()
    
#     sandbox = False
#     today = dt.datetime.now()
#     date = today - relativedelta(months=1)

#     if args.sandbox:
#         sandbox = True

#     if args.date:
#         components = args.date.split('-')
#         year = int(components[0])
#         month = int(components[1])
#         day = int(components[2])
#         date = dt.datetime(year, month, day)
#     else:
#         print('No date provided - uploading {0} netCDFs to Zenodo'.format(date.strftime("%Y/%m")))
    
#     main(date, sandbox)









