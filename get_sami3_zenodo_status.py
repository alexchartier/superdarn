#!/usr/bin/env python3
"""
Starting at 2019-03 and stepping one day at a date
to the present, look at the SAMI3 data stored on Zenodo and
create a json file specifying whether data exists for each day.
"""

__author__ = "Jordan Wiker"
__copyright__ = "Copyright 2023, JHUAPL"
__version__ = "1.0.0"
__maintainer__ = "Jordan Wiker"
__email__ = "jordan.wiker@jhuapl.edu"
__status__ = "Development"

import requests
import json
import datetime
import time
import helper

DATA_STATUS_DIR = '/project/superdarn/data/data_status/sami3_data_status'

# Define the start and end dates
START_DATE = datetime.datetime(2019, 3, 1)
END_DATE = datetime.datetime.today()

# Initialize data dictionary
data = {}

# Loop through each day
date = START_DATE
while date <= END_DATE:
    day = date.strftime('%Y-%b-%d')
    print('Getting SAMI3 Zenodo data for {}'.format(day))

    response = requests.get('https://zenodo.org/api/records',
                            params={'q': '"SAMI3 data in netCDF format ({})"'.format(day),
                                    'access_token': helper.ZENODO_TOKEN})
    # Extract rate-limit information from response headers
    rate_limit_remaining = int(
        response.headers.get("X-RateLimit-Remaining", 0))
    rate_limit_reset = int(response.headers.get("X-RateLimit-Reset", 0))
    # print(rate_limit_remaining)

    data[day] = 1 if response.json()["hits"]["hits"] else 0

    if rate_limit_remaining == 1:
        current_time = int(time.time())
        sleep_time = rate_limit_reset - current_time
        print("Rate limit about to be exhausted. Waiting for {} seconds...".format(
            sleep_time))
        time.sleep(sleep_time)

    date += datetime.timedelta(days=1)

# Save data to the JSON file
outputFile = '{0}/{1}_sami3_zenodo_data_inventory.json'.format(
    DATA_STATUS_DIR, END_DATE.strftime('%Y%m%d'))
with open(outputFile, 'w') as outfile:
    json.dump(data, outfile)

# print("Data saved to {}".format(outputFile))
