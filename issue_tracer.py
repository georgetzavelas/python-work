#!/bin/python
"""
This script attempts to collect log information for a specific MSISDN or for a specific time interval.
- input: MSISDN and/or date/time
    - if MSISDN is not provided look for events around alarm conditions
    - if date is missing assume today
    - if time is missing then assume all day
- output: capture logs and log snippets for the relavent time/alarm
    - user logs
    - main log
    - ussd log
    - smpp log
    - accesspool log
- search for log files

"""
import os
import sys
from datetime import date, datetime, timedelta
from optparse import OptionParser

# assumption that this is running from the TCS directory
TCS_LOG_DIRECTORY = './log'
TCS_SERVER_SUBDIRECTORY = '/server'
USSD_LOG = 'TCS.ussd'
MAIN_LOG = 'TCS.log'
FUNCTION_LOG = 'TCS.function'
SMPP_LOG = 'TCS.smpp'


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    opts, args = parse_args(argv)
    looking_for = ''
    if opts.msisdn is not None:
        looking_for = 'looking for msisdn=' + opts.msisdn
    else:
        print('msisdn missing, use -m to specify')
        return -1
    if opts.date is not None:
        looking_for += ', date=' + opts.date
    if opts.time is not None:
        looking_for += ', time=' + opts.time
    print(looking_for)
    extract_server_log(MAIN_LOG, opts)
    extract_server_log(USSD_LOG, opts)
    extract_server_log(FUNCTION_LOG, opts)
    extract_server_log(SMPP_LOG, opts)
    return 0


def extract_server_log(log_name, opts):
    def log_subdirs_exist():
        return os.path.isdir(TCS_LOG_DIRECTORY + TCS_SERVER_SUBDIRECTORY)

    log_dir = TCS_LOG_DIRECTORY
    if log_subdirs_exist():
        log_dir = TCS_LOG_DIRECTORY + TCS_SERVER_SUBDIRECTORY
    if opts.date is not None:
        find_date = datetime.strptime(opts.date,'%y-%m-%d')
    if opts.time is not None:
        find_time = datetime.strptime(opts.time,'%H:%M')
        start_time_window = (find_time - timedelta(minutes=2)).time()
        end_time_window = (find_time + timedelta(minutes=2)).time()
    for i in range(9, -1, -1):
        filename = log_dir + '/' + log_name + '.' + str(i)
        if not os.path.isfile(filename):
            continue
        occurrences = 0
        with open(filename) as f:
            for line in f:
                line = line.strip('\n')
                if not line[0:1].isdigit() or len(line) < 18:
                    continue
                else:
                    try:
                        timestamp = datetime.strptime(line[:17],'%d-%m-%y %H:%M:%S')
                        if find_date is not None:
                            # print('timestamp=' + str(timestamp.date()) + ', find_date=' + str(find_date.date()))
                            if timestamp.date() != find_date.date():
                                continue
                            if find_time is not None:
                                if timestamp.time() >= start_time_window and timestamp.time() <= end_time_window:
                                    continue
                    except ValueError:
                        pass
                    new_occurrence = 0
                    if log_name == MAIN_LOG:
                        new_occurrence = analyze_server_log(line, opts)
                    elif log_name == USSD_LOG:
                        new_occurrence = analyze_ussd_log(line, opts)
                    elif log_name == FUNCTION_LOG:
                        new_occurrence = analyze_function_log(line,opts)
                    elif log_name == SMPP_LOG:
                        new_occurrence = analyze_smpp_log(line,opts)
                    if new_occurrence > 0:
                        occurrences += new_occurrence
                        print(line)
        if occurrences > 0:
            print('found ' + str(occurrences) + ' occurrences in file:' + filename)


def analyze_server_log(line, opts):
    # Success examples:
    # TCS.log.0: 14-03-16 06:07:12:INFO:Login from E_USSD_250725641341

    # Failure examples:
    # 14-03-16 06:08:44:WARNING:SystemFraudAlarm
    # 14-03-16 06:07:43:WARNING:Errors:
    # E_USSD_250727236067     2
    # E_USSD_250725273510     1

    parts = line[19:].split(':')
    if len(parts) < 2:
        return 0
    if parts[1].find(opts.msisdn) > -1:
        return 1
    return 0


def analyze_ussd_log(line, opts):
    # Success examples
    # 16-03-16 20:26:53:INFO:Menu Msg from:250725139602,d_id:370,msg:********
    # 16-03-16 20:26:53:INFO:Menu Msg to:250725139602,d_id:370,menu:28,alive:12
    # 16-03-16 20:26:53:INFO:Cell tower info for msisdn 250725303344 is 48051:2216:13:635 [13186ms, src=250727726367]
    # 16-03-16 20:26:53:INFO:Rcvd ATI msisdn:250725303344,d_id:31,mcc:635,mnc:13,lac:2216,ci:48051
    # 16-03-16 20:26:53:INFO:Executing [250727010046] from access pool, d_id=371
    # 16-03-16 20:26:53:INFO:Sent SRISM msisdn:250726568193,d_id:380
    # 16-03-16 20:26:53:INFO:Rcvd SRISM msisdn:250727295888,d_id:377,mscGT:null
    # 16-03-16 20:26:53:INFO:Sent SMS-DELIVER msisdn:250725588689,d_id:299,msg:1/2
    # 16-03-16 20:26:58:INFO:SMS successfully sent via embedded SMS: msisdn=250725588689, d_id=299

    # Failure examples
    # 16-03-16 20:26:53:WARNING:processDialogueIndEvent error: TC-U-ABORT received
    # 16-03-16 20:26:53:WARNING: -> d_id=8054, reason=User Specific
    # 16-03-16 20:26:58:WARNING:processComponentIndEvent error: TC-L_CANCEL (timer reset) for d_id=7169, i_id=1
    # 16-03-16 20:26:58:WARNING:Sending Abort for d_id=7169
    # 16-03-16 20:27:01:WARNING:processDialogueIndEvent error: TC-NOTICE received (unable to deliver msg)
    # 16-03-16 20:27:01:WARNING: -> d_id=485, cause=[11]
    # 16-03-16 20:27:01:WARNING:Simulating Component Error:1
    # 16-03-16 20:27:01:WARNING:processMapError: received error [Unknown Error] while attempting SMS for MSISDN [250726127570]
    # 16-03-16 20:27:01:INFO:Calling the onFailure listener for SMS partition 1/2

    parts = line[19:].split(':')
    if len(parts) < 2:
        return 0
    info = ':'.join(parts[1:])
    if info.find(opts.msisdn) > -1:
        return 1
    return 0


def analyze_function_log(line, opts):
    parts = line[19:].split(',')
    if len(parts) < 2:
        return 0
    if parts[1].find(opts.msisdn) > -1:
        return 1
    return 0


def analyze_smpp_log(line, opts):
    # success examples
    # 16-03-16 18:21:52:INFO:Attempting message 4 to 250726527486 seq 75459 at 1458145312069 [PROD_SMSC]
    # 16-03-16 18:21:52:INFO:Sending Multipart SMS with msgRef=31749 parts=2
    # 16-03-16 18:21:52:INFO:Attempting message 4 to 250726527486 seq 75459 at 1458145312069 [PROD_SMSC]
    # 16-03-16 18:21:52:INFO:Attempting message 4 to 250726527486 seq 75460 at 1458145312069 [PROD_SMSC]
    # 16-03-16 18:21:52:INFO:End Multipart SMS for msgRef=31749

    # failure examples
    # 16-03-16 18:21:51:WARNING:SMPP submit error [PROD_SMSC]: 20 sequence 75458 debug string (submit_resp:
    #   (pdu: 16 80000004 14 75458)  )  CommandStatus{name=ESME_RMSGQFUL, errorCode=0x00000014,
    #   description=Message Queue Full}
    # 16-03-16 18:21:52:INFO:SMS message part 1/1 failed via USSD; attempting to send via SMPP

    parts = line[19:].split(':')
    if len(parts) < 2:
        return 0
    if parts[1].find(opts.msisdn) > -1:
        return 1
    return 0


def parse_args(argv):
    if argv is None:
        argv = sys.argv[1:]
    p = OptionParser('usage: %prog [OPTIONS]', version='%prog 1.0')
    p.add_option('-m', '--msisdn', action='store', type='string', dest='msisdn',
                 help='MSISDN to look for')
    p.add_option('-d', '--date', action='store', type='string', dest='date', default=date.today().strftime('%d-%m-%y'),
                 help='date to search for, format DD-MM-YY')
    p.add_option('-t', '--time', action='store', type='string', dest='time',
                 help='time to search for +/- 2 minutes, format HH:MM')
    opts, args = p.parse_args(argv)
    return opts, args

if __name__ == '__main__':
    main()