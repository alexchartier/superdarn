import sys
import filecmp
import os
import datetime

# Set up email message parameters
emailSubject   = ''
emailBody      = ''
emailAddresses = 'jordan.wiker@jhuapl.edu'#,Alex.Chartier@jhuapl.edu'


emailSubject = '"email test"'
emailBody    = '"Email test"'

def send_email(subject, body, addresses):
    os.system('echo {bd} | mail -s {sub} {addr}'.format(bd = body, sub = subject, addr = addresses))

send_email(emailSubject, emailBody, emailAddresses)








