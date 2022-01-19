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
sys.path.append('/usr/lib/python2.7/site-packages/')
import requests
import datetime as dt
from dateutil.relativedelta import relativedelta
import argparse
import helper
    
__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2022, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

# TODO: Add non-sandbox Zenodo token, and confirm deposit:write is enabled
ZENODO_TOKEN = ''
ZENODO_SANDBOX_TOKEN = '9FWXXWi1NYeEo6c7zarVtOEOzUkPwiwgVNJ6FD2Wyzecf3PNrs1HKKnrDjYS'

def main(
    date = dt.datetime(2020, 7, 1),
    sandbox = True
):
    accessToken = ZENODO_SANDBOX_TOKEN if sandbox else ZENODO_TOKEN
    uploadDir = date.strftime(helper.NETCDF_DIR_FMT)
    print(date)
    print(uploadDir)
    print(sandbox)
    

def _build_arg_parser(Parser, *args):
    scriptname = os.path.basename(sys.argv[0])

    formatter = argparse.RawDescriptionHelpFormatter(scriptname)
    width = formatter._width

    title = "zenodo_uploader"
    copyright = "Copyright (c) 2022 JHU/APL"
    shortdesc = "Upload SuperDARN netCDF files to Zenodo"
    desc = "\n".join(
        (
            "*" * width,
            "*{0:^{1}}*".format(title, width - 2),
            "*{0:^{1}}*".format(copyright, width - 2),
            "*{0:^{1}}*".format("", width - 2),
            "*{0:^{1}}*".format(shortdesc, width - 2),
            "*" * width,
        )
    )

    usage = (
        "%s [sandbox] [-d YYYY-m-d]" % scriptname
    )

    # parse options
    parser = Parser(
        description=desc,
        usage=usage,
        prefix_chars="-+",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="""Upload to the APL Sandbox Zenodo account""",
    )

    parser.add_argument(
        "-d",
        "--date",
        dest="date",
        default=None,
        help="""Month to upload - format: 'YYYY-m-d'""",
    )

    return parser


if __name__ == '__main__':
    parser = _build_arg_parser(argparse.ArgumentParser)
    args = parser.parse_args()
    
    sandbox = False
    today = dt.datetime.now()
    date = today - relativedelta(months=1)

    if args.sandbox:
        sandbox = True

    if args.date:
        components = args.date.split('-')
        year = int(components[0])
        month = int(components[1])
        day = int(components[2])
        date = dt.datetime(year, month, day)
    else:
        print('No date provided - uploading {0} netCDFs to Zenodo'.format(date.strftime("%Y/%m")))
    
    main(date, sandbox)









