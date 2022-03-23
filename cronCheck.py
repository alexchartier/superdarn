import subprocess
import os
import helper

EMAIL_ADDRESSES = 'jordan.wiker@jhuapl.edu, jordan.wiker@gmail.com'

p = subprocess.Popen(['ps', '-A'], stdout=subprocess.PIPE)
numCronResults = 0
out, err = p.communicate()
for line in out.decode("utf-8").splitlines():
    if "crond" in line:
        numCronResults += 1

if numCronResults < 3:
    emailSubject = '"Scripts Stopped Running"'
    emailBody    = '"Cron scripts are no longer running"'
    helper.send_email(emailSubject, emailBody, EMAIL_ADDRESSES)
