#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Generates report on what was processed for CR-R1 by RuleEngine.

Created on Mon Mar 10 11:05:21 2014

@author: kevin.xu
"""
#TODO: test transfer pending, cr776 error, and also try the commands in the logs
import os
import sys
import re
import subprocess
import logging
import thread

logger = None
"Redirects stderr for smtplib only"
class WriterToLogger():
    def write(self, data):
        logger.debug(data)
sys.stderr = WriterToLogger()
import smtplib
sys.stderr = sys.__stderr__

import traceback
import pprint
import pytz
from datetime import datetime, timedelta
from pytz import timezone
from optparse import OptionParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

"""Constants definitions"""
DIR_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if sys.platform == 'win32':
    DIR_BASE = os.getcwd()
DIR_UL = os.path.join(DIR_BASE, "uploaded")
DIR_DL_PROC = os.path.join(DIR_BASE, "downloaded", "processed")
DIR_DL_ERR = os.path.join(DIR_BASE, "downloaded", "error")
DIR_DL_RESP = os.path.join(DIR_BASE, "downloaded", "response")
LOG_EXECUTION = os.path.join(DIR_BASE, "log", "scbank_log_reporter.log")
LOG_SCBANK_FTP = os.path.join(DIR_BASE, "log", "scbank_sftp.log")
FORMAT_LOGGING = '%(asctime)-15s[%(levelname)s](P%(process)d/T%(thread)d): %(message)s'
FMT_ARG_TIMESTAMP = "%Y-%m-%d_%H.%M.%S"
FMT_UNFETCHED_FI_TS = "%Y-%m-%d %H:%M"
FNAME_ACCT_OPEN_CLOSE = "acct_open_close"
FNAME_ACCT_STATIC_DATA_CHANGE = "acct_static_data_changes"
FNAME_ACCT_REJECT = "acct_reject"


"""Regex Patterns definition"""
PAT_UPLOAD = re.compile(r".*Uploading\s(.+)\sto /tft_in")
PAT_DOWNLOAD = re.compile(r".*Fetching\s/(.+)\sto")
PAT_TS_ARG = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2})")
PAT_TS_LOG = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}),")
PAT_FI_PAYMENT = re.compile(r"^(payment\.\d+\.H2H-UA-00003)$")
PAT_FI_PAYEE = re.compile(r"^(payee\.\d+\.H2H-UA-00004)$")
PAT_FI_BANSTA = re.compile(r".+BANSTA.+")
PAT_FI_ACKREJ = re.compile(r"(pay.+\.(ack|rej)[23])")
PAT_FI_REJ = re.compile(r"(pay.+\.rej[23])")
PAT_EMAIL = re.compile(r"^[^\s,;]+@[^\s,;]+$")
PAT_CR776_FILE = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.acct_.+")
PAT_CR776_REQ = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.(acct_.+)\.csv$")
PAT_CR776_RESP = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.(acct_.+)\.H2H-.{3}-.{3}$")
PAT_CR776_RESP_REJ = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.(acct_.+)\.H2H-.{3}-.{3}.rej2$")
PAT_CR776_ACKS = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.(acct_.+)\.(ack|rej)[23]$")
PAT_IGNORE_EBNK = re.compile(r"^(?:GSGTELEQ|GSTRTRK1)\.EBNK\d+\.csv$")

PAT_IGNORE_FILENAMES = [ PAT_IGNORE_EBNK ]

class SystemStatusAnalyzer(object):
    PAT_SFTP_LS = re.compile( r"^\S{10}\s+\S+\s\S+\s+\S+\s+\S+\s+(\S+\s+\S+\s+\S+)\s(.+)$")
    PAT_MOUNT_CAPACITY = re.compile( R'^(\d+)%\s+(.+)$' )
    SH_MOUNT_CAPACITY = r"df -h | tr -s ' ' | cut -d ' ' -f 5,6"
    FMT_LS_TS_NOYEAR = "%b %d %H:%M"
    FMT_LS_TS_NOTIME = "%b %d %Y"
    CMD_SFTP = None

    def __init__(self):
        self._setupCommandPath()

    def _setupCommandPath(self):
        if not self.CMD_SFTP:
            proc = subprocess.Popen('which sftp', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            assert stderr.strip() == ""
            self.CMD_SFTP = stdout.strip()

    def getMountPointsAboveCapacity(self, capacityThreshold):
        ret = []
        proc = subprocess.Popen(self.SH_MOUNT_CAPACITY, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        for line in stdout.strip().split('\n')[1:]:    #skip header
            line = line.strip();
            #logger.info("DF OUTPUT LINE: "+line)
            matcher = self.PAT_MOUNT_CAPACITY.match(line)
            if matcher:
                capacityStr = matcher.group(1)
                mountPt = matcher.group(2)
                capacity = float(capacityStr)
                if capacity >= capacityThreshold:
                    ret.append((mountPt, capacity))
            else:
                logger.error("df output line does not match expected: %s"%line)
        return ret

    def _getSFtpSubprocess(self, host, port, timeout, username):
        return subprocess.Popen([self.CMD_SFTP,
                                 '-oPort=%d'%port,
                                 '-oConnectTimeout=%d'%timeout,
                                 '%s@%s'%(username, host)],
                                shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.PIPE)

    def isSFtpConnectable(self, host, port, username):
        #NOTE: pwd is ignored at the moment, as sftp don't take in pwd in automated way
        proc = self._getSFtpSubprocess(host, port, 5, username)
        try:
            stdout, stderr = proc.communicate("quit\n")
        except OSError, e:
            logger.debug("Caught OSError in isSFtpConnectable(): %s"%e)
            return False
        return proc.poll() == 0

    def getSFtpFileOlderThan(self, host, port, directory, timeDelta, username, serverTzStr):
        ret = []
        logger.info("In getSftpFileOlderThan(), assuming sftp server to be in %s tz"%serverTzStr)
        serverTz = timezone(serverTzStr)
        utcTz = timezone("UTC")
        #WARNING: when there is a transition between DST, exception is raise, avoid running script during that DST switch time
        now = utcTz.localize( datetime.utcnow() ).astimezone(serverTz)
        proc = self._getSFtpSubprocess(host, port, 5, username)

        try:
            stdout, stderr = proc.communicate("ls -l %s\nquit\n"%directory )
            if stdout.startswith("sftp>"):      #Clears initial Prompt
                stdout = stdout[5:]
            #print "stdout => \n" + stdout
            lines = [ i.strip() for i in stdout.split('\n')]
            for fLine in lines:
                if fLine == "sftp>" or fLine.startswith("d") or fLine == "":
                    continue
                matched = self.PAT_SFTP_LS.search(fLine)
                if not matched:
                    logger.warning("SFTP ls output line did not match regex: "+fLine)
                    continue
                tsStr = matched.group(1)
                fName = matched.group(2)

                tsStr = " ".join( [i for i in tsStr.split(' ') if i.strip()])
                tsObj = None
                if ":" in tsStr:
                    tsObj = datetime.strptime(tsStr, self.FMT_LS_TS_NOYEAR)
                    tsObj = tsObj.replace(year=now.year)
                else:
                    tsObj = datetime.strptime(tsStr, self.FMT_LS_TS_NOTIME)
                #assign proper timezone info
                tsObj = serverTz.localize( tsObj )

                #convert to utc before arithmetic to avoid trouble
                if (now.astimezone(utcTz) - tsObj.astimezone(utcTz)) > timeDelta:
                    ret.append( (fName, tsObj) )
        except OSError, e:
            logger.debug("Caught OSError in getSFtpFileOlderThan(): %s"%e)
        return ret

class FileProcessState(object):
    def __init__(self, f, p, e, o = 1):
        self.fileName = f
        self.processed = p
        self.expectedPath = e
        self.responsesRecv = []
        self.occurNum = o
        self.isTransferPending = False  #specifically for CR776

    def isInExpectedPath(self):
        return os.path.exists(self.expectedPath)

    def getFileByteSize(self):
        ret = 0
        if self.isInExpectedPath():
            fileStat = os.stat(self.expectedPath)
            ret = fileStat.st_size
        return ret
    
    def isFileEmpty(self, ignoreWhiteSpace=True):
        if self.getFileByteSize() == 0:
            return True
        else:
            fi = open(self.expectedPath)
            try:
                fiContent = fi.read().strip()
                return len(fiContent) == 0
            finally:
                fi.close()
    
    def getLineCount(self):
        ret = 0
        if self.isInExpectedPath():
            fi = open(self.expectedPath)
            try:
                ret = len( fi.read().strip().split('\n') )
            finally:
                fi.close();
        return ret


class ErrorReport(object):
    def __init__(self, ti, desc, dbg):
        self.title = ti
        self.description = desc
        self.debugMsg = dbg

class AutomationSummaryProcessor(object):
    _FMT_TS_LOG = "%Y-%m-%d_%H:%M:%S"
    _DAYS_PRIOR_FILE_DUPLICATES = 13

    """
    Create a processor that generates a summary of files processed by RuleEngine
    for CR-R1 during a period of time.

    @type beginTime: datetime.datetime
    @param beginTime: the start time of the search
    @type endTime: datetime.datetime
    @param endTime: the end time of the search
    """
    def __init__(self, beginTime, endTime, logFilePath):
        self._timeRangeBegin = beginTime
        self._timeRangeEnd = endTime
        self._logFilePath = logFilePath
        self._processingDone = False
        self._filesTransferred = { 'ul':[], 'dl':[] }
        self._priorFilesTransferred = None

        'CR-R1'
        self._crr1FilesTransferred = { 'ul':[], 'dl':[] }
        self._crr1UnprocessedFiles = { 'ul':[], 'dl':[] }
        self._crr1ErrorList = []
        self._payeeFileResults = []
        self._paymentFileResults = []
        self._banstaFileResults = []
        self._extraAckFileList = []

        'CR-776'
        self._cr776FilesTransferred = { 'ul':[], 'dl':[] }
        self._cr776UnprocessedFiles =  { 'ul':[], 'dl':[] }
        self._cr776ErrorList = []
        self._acctOpenCloseReqResults = []
        self._acctRejectReqResults = []
        self._acctStaticChangeReqResults = []
        self._acctOpenCloseRespResults = []
        self._acctRejectRespResults = []
        self._acctStaticChangeRespResults = []

    def _getOccurrenceCount(self, fileList):
        counter = {}
        for f in fileList:
            counter[f] = counter.get(f,0)+1
        return counter

    """
    Searches for the files transferred to/from the SFTP server. Their filename
    is saved into the dictionary self._filesTransferred on 'ul' and 'dl' entries.
    """
    def _searchFilesTransferred(self, timeRangeBegin, timeRangeEnd):
        tsStartStr = timeRangeBegin.strftime(self._FMT_TS_LOG)
        tsEndStr = timeRangeEnd.strftime(self._FMT_TS_LOG)
        foundBegin = False
        foundEnd = False
        retFileTransferred = { 'ul':[], 'dl':[] }

        fi = open(self._logFilePath)
        try:
            for line in fi:
                tsMatch = PAT_TS_LOG.match(line)
                if tsMatch:
                    if not foundBegin:
                        if tsMatch.group(1) > tsStartStr:
                            foundBegin = True
                            logger.info("Begin Searching for transferred files between %s and %s"%(tsStartStr, tsEndStr))
                    else:
                        if not foundEnd and tsMatch.group(1) > tsEndStr:
                            foundEnd = True
                        if foundEnd:
                            break
                if not foundBegin:
                    continue
                upMatch = PAT_UPLOAD.match(line)
                downMatch = PAT_DOWNLOAD.match(line)
                if upMatch:
                    retFileTransferred['ul'].append(upMatch.group(1))
                    logger.info("UL: " + upMatch.group(1))
                elif downMatch:
                    retFileTransferred['dl'].append(downMatch.group(1))
                    logger.info("DL: " + downMatch.group(1))
        finally:
            fi.close()
        logger.info("Finished transferred files searches.")
        return retFileTransferred


    """
    Record all CR-776 downloaded and uploaded. The number of times uploaded, downloaded,
    and whether if they are in the expected storage folder is recorded.

    @param filesTransferred: list of files transferred, of form {'ul':[], 'dl':[] }
    @type filesTransferred: dict
    """
    def _processCr776FilesTransferred(self, filesTransferred):
        ulFileOccurrence = self._getOccurrenceCount(filesTransferred['ul'])
        dlFileOccurrence = self._getOccurrenceCount(filesTransferred['dl'])

        'Categorize all of the files downloaded and uploaded for Cr776'
        for fileOccurrence, fnameMatchTuples, patIgnore, expectedDir, patMatch, transferType, uldl \
        in ((ulFileOccurrence, ((FNAME_ACCT_OPEN_CLOSE, self._acctOpenCloseRespResults ),
                                (FNAME_ACCT_STATIC_DATA_CHANGE, self._acctStaticChangeRespResults),
                                (FNAME_ACCT_REJECT, self._acctRejectRespResults )),
             None, DIR_UL, PAT_CR776_RESP, 'uploaded', 'ul'),
            (dlFileOccurrence, ((FNAME_ACCT_OPEN_CLOSE, self._acctOpenCloseReqResults ),
                                (FNAME_ACCT_STATIC_DATA_CHANGE, self._acctStaticChangeReqResults),
                                (FNAME_ACCT_REJECT, self._acctRejectReqResults )),
             PAT_CR776_ACKS, DIR_DL_PROC, PAT_CR776_REQ, 'downloaded', 'dl')):
            for fileName, ct in fileOccurrence.items():
                state = FileProcessState(fileName, False, os.path.join(expectedDir, fileName), ct)
                match = patMatch.match(fileName)
                if match:
                    for (prefix, saveList) in fnameMatchTuples:
                        if match.group(1).startswith(prefix):
                            state.processed = True
                            saveList.append(state)
                elif patIgnore and patIgnore.match(fileName):
                    state.processed = True
                    #ignore the acks and rejs

                if state.processed == False:
                    self._cr776UnprocessedFiles[uldl].append(state)
                    self._cr776ErrorList.append(
                        ErrorReport("Unexpected file %s"%transferType,
                        "File %s not matching any expected: %s" % (transferType, fileName), ""))

        "Check if the downloads are the path expected"
        for resultList in [ self._acctOpenCloseReqResults, self._acctRejectReqResults,
                            self._acctStaticChangeReqResults]:
            for idx, state in enumerate(resultList):
                if not state.isInExpectedPath():
                    state.processed = False
                    self._cr776UnprocessedFiles['dl'].append(state)
                    self._cr776ErrorList.append( ErrorReport("File downloaded not found in storage folder",
                        "File not found in downloaded storage folder: %s" % (state.fileName,), ""))

        "Check if the upload are the path expected. if not, are they in the response folder"
        for resultList in [ self._acctOpenCloseRespResults, self._acctRejectRespResults,
                            self._acctStaticChangeRespResults]:
            for idx, state in enumerate(resultList):
                if not state.isInExpectedPath():
                    if os.path.exists( os.path.join( DIR_DL_RESP, state.fileName )):
                        state.isTransferPending = True
                    else:
                        state.processed = False
                        self._cr776UnprocessedFiles['ul'].append(state)
                        self._cr776ErrorList.append( ErrorReport("File uploaded not found in storage folder",
                            "File not found in uploaded storage folder: %s" % (state.fileName,),
                            ""))

        "Check if the downloaded files have been downloaded previously."
        self._cr776ErrorList += self._genErrorForFilePreviouslyTransferred('dl', filesTransferred['dl'])

    """
    Process the ul and dl files according to the CR-R1 specification, looking for
    anomanlies. It does the following:
    1. Record any non-payment, non-payee files uploaded as error
    2. Check if the payment, payee uploads are archived in the expected location.
       If they are, it means they had been uploaded successfully. if not, then
       record as error.
    3. Check if there were ack2 and ack3 received for the payment, payee files uploaded.
    4. Check if there are invalid ack+rej combinations, if so, then record as
       error.
    5. Record any non-bansta, non-ack, and non-rej files downloaded as error.
    6. Record all bansta, ack, rej files downloaded.

    @param filesTransferred: list of files transferred, of form {'ul':[], 'dl':[] }
    @type filesTransferred: dict
    """
    def _processCrR1FilesTransferred(self, filesTransferred):
        def getExpectedAbsoluteDlPath(filename):
            if PAT_FI_REJ.match(filename):  #reject file, expect
                return os.path.join( DIR_DL_ERR, filename )
            else:
                return os.path.join( DIR_DL_PROC, filename )


        "Find out all of the duplicated files downloaded and uploaded"
        ulFileOccurrence = self._getOccurrenceCount(filesTransferred['ul'])
        dlFileOccurrence = self._getOccurrenceCount(filesTransferred['dl'])
        for transferType, occurrenceCounts in ( ("uploaded", ulFileOccurrence),
                                                ('downloaded', dlFileOccurrence) ):
            duplicateCount = sum([ ct for ct in occurrenceCounts.values() if ct > 1])
            if duplicateCount > 0:
                duplicateFilesStr = ", ".join([ "%s(%dx)"%(fname,ct) for fname, ct in occurrenceCounts.items() if ct > 1])
                self._crr1ErrorList.append(ErrorReport("Duplicated files %s within report period." % transferType,
                                               "Found %d duplicated files %s: %s" % (duplicateCount, transferType, duplicateFilesStr ),
                                               ""))

        ulStates = dict([ (f, FileProcessState(f, False, os.path.join(DIR_UL, f), ulFileOccurrence[f] ) )
                         for f in filesTransferred['ul'] ])
        dlStates = dict([ (f, FileProcessState(f, False, getExpectedAbsoluteDlPath(f), dlFileOccurrence[f] ) )
                         for f in filesTransferred['dl'] ])

        "Find all payee and payment files uploaded, and whether if ack2 and ack3 is received"
        for fName, state in ulStates.items():
            paymentMatch = PAT_FI_PAYMENT.match(fName)
            payeeMatch = PAT_FI_PAYEE.match(fName)

            # if files other than payment and payees are uploaded
            if not paymentMatch and not payeeMatch:
                self._crr1UnprocessedFiles['ul'].append(state)
                self._crr1ErrorList.append(ErrorReport("Non-payee/payment file uploaded",
                                               "Unexpected file uploaded: %s" % fName, ""))
                continue

            # Check: If uploaded successfully, should be in uploaded folder
            if not state.isInExpectedPath():
                self._crr1UnprocessedFiles['ul'].append(state)
                self._crr1ErrorList.append(ErrorReport("File possibly not uploaded successfully",
                                               "This file was not found in upload archive: %s" % fName, ""))
                continue

            for matchObj in [payeeMatch, paymentMatch]:
                if not matchObj:
                    continue

                for ext in ['ack2', 'ack3', 'rej2', 'rej3']:
                    respFiName = matchObj.group(1) + "." + ext
                    if dlStates.has_key(respFiName):
                        state.responsesRecv.append(ext)
                        tmpIsInPath = dlStates[ respFiName ].isInExpectedPath()
                        dlStates[ respFiName ].processed = tmpIsInPath
                        if ext == 'rej2' or ext == 'rej3':
                            self._crr1ErrorList.append(ErrorReport("%s Received"%ext,
                                                   "Reject file %s was received" % respFiName, ""))
                invalidComboFound = False
                for k1, k2 in [('ack2', 'rej2'), ('ack3', 'rej3'), ('ack3', 'rej2')]:
                    if k1 in state.responsesRecv and k2 in state.responsesRecv:
                        self._crr1UnprocessedFiles['ul'].append(state)
                        self._crr1ErrorList.append(ErrorReport("Invalid ack+rej files combination",
                                               "%s have received response %s and %s" % (fName, k1, k2), ""))
                        invalidComboFound = True
                        break
                if not invalidComboFound:
                    state.processed = True

            if state.processed:
                if payeeMatch:
                    self._payeeFileResults.append(state)
                elif paymentMatch:
                    self._paymentFileResults.append(state)

        "Report on the contents of the BANSTA files"
        for fName,state in dlStates.items():
            if state.processed:
                continue

            # Check: If processed correctly, should be in downloaded/processed folder
            if not state.isInExpectedPath():
                self._crr1UnprocessedFiles['dl'].append(state)
                self._crr1ErrorList.append(ErrorReport("Downloaded file possibly not processed successfully",
                                               "This file was not found in process storage folder: %s" % fName, ""))
                continue

            banstaMatch = PAT_FI_BANSTA.match(fName)
            ackRejMatch = PAT_FI_ACKREJ.match(fName)
            if banstaMatch:
                state.processed = True
                self._banstaFileResults.append(state)
            elif ackRejMatch:
                state.processed = True
                self._extraAckFileList.append(state)
            else:
                self._crr1UnprocessedFiles['dl'].append(state)
                self._crr1ErrorList.append(ErrorReport("Unexpected file downloaded",
                                               "This file is not expected: %s" % fName, ""))
                continue

    """
    Determines if the same file have been downloaded or uploaded within a prior time range.

    @param fileName: name of the file
    @param expXferDir: file transfer direction. valid values are 'ul' and 'dl'.
    """
    def _isFilePreviouslyTransferred(self, fileName, expXferDir=None):
        if not self._priorFilesTransferred:
            #Find and store the set of files downloaded or uploaded previously within X days
            prevFileTimeRangeStart = self._timeRangeBegin - timedelta(days=self._DAYS_PRIOR_FILE_DUPLICATES)
            prevFileTimeRangeEnd = self._timeRangeBegin
            prevFileXferList = self._searchFilesTransferred(prevFileTimeRangeStart, prevFileTimeRangeEnd)

            self._priorFilesTransferred = { 'ul':{}, 'dl':{} }
            for xferDir, fileList in prevFileXferList.items():
                for fileElm in fileList:
                    self._priorFilesTransferred[xferDir][fileElm] = True
            pprint.pprint(self._priorFilesTransferred)
        if expXferDir:
            print  "%s transferred previously: %s"%( fileName, self._priorFilesTransferred[expXferDir].has_key(fileName) )
            return self._priorFilesTransferred[expXferDir].has_key(fileName)
        else:
            return self._priorFilesTransferred['ul'].has_key(fileName) \
                or self._priorFilesTransferred['dl'].has_key(fileName)

    def _getFileTransferDescription(self, xferDir):
        return {'ul':"uploaded", 'dl':"downloaded"}[xferDir]

    """
    Check a list of files to see if they were previously transfered. Generate ErrorReport for each that is.

    @param xferDir: file transfer direction. can be either 'ul' or 'dl'
    @param fileList: list of file names to check for
    """
    def _genErrorForFilePreviouslyTransferred(self, xferDir, fileList):
        ret = []
        xferDesc = self._getFileTransferDescription(xferDir)
        errorTitle = "File with identical name previously %s in last %s days"%(xferDesc, self._DAYS_PRIOR_FILE_DUPLICATES)
        for fileName in fileList:
            if self._isFilePreviouslyTransferred(fileName, xferDir):
                errorDesc = "%s was %s previously"%(fileName, xferDesc)
                ret.append( ErrorReport(errorTitle, errorDesc, "") )
        return ret


    """
    Process all the files transfers, and report back how many files transferred
    """
    def process(self):
        if not self._processingDone:
            #Find all files uploaded and downloaded within the specified period
            self._filesTransferred = self._searchFilesTransferred(self._timeRangeBegin, self._timeRangeEnd)
            #sort files into different task type
            for transferType, fileList in self._filesTransferred.items():
                for fileName in fileList:
                    #Ignore files
                    ignored = False
                    for pattIgnore in PAT_IGNORE_FILENAMES:
                        if pattIgnore.match(fileName):
                            logger.debug("Ignoring File %s"%fileName)
                            ignored = True
                            break
                    if ignored:
                        continue
                    #Sorting files into categories
                    if PAT_CR776_FILE.match(fileName):
                        self._cr776FilesTransferred[transferType].append(fileName)
                    else:
                        self._crr1FilesTransferred[transferType].append(fileName)

            #pass the files transferred into respective functions
            self._processCrR1FilesTransferred(self._crr1FilesTransferred)
            self._processCr776FilesTransferred(self._cr776FilesTransferred)
            self._processingDone = True
        return len( self._filesTransferred['ul'] ) + len( self._filesTransferred['dl'] )

    'CR-R1 Getters'
    def getCrR1ErrorList(self):
        return self._crr1ErrorList

    def getPayeeFilesResult(self):
        return self._payeeFileResults

    def getPaymentFilesResult(self):
        return self._paymentFileResults

    def getBanstaFilesResult(self):
        return self._banstaFileResults

    def getExtraAcksFilesList(self):
        return self._extraAckFileList

    def getCrR1UnprocessedFileList(self):
        return self._crr1UnprocessedFiles

    def getProcessedTimeRange(self):
        return (self._timeRangeBegin, self._timeRangeEnd)

    'CR-776 Getters'
    def getCr776ErrorList(self):
        return self._cr776ErrorList

    def getCr776UnprocessedFileList(self):
        return self._cr776UnprocessedFiles

    def getAcctOpenCloseRequestResult(self):
        return self._acctOpenCloseReqResults

    def getAcctRejectRequestResult(self):
        return self._acctRejectReqResults

    def getAcctStaticDataChangeRequestResult(self):
        return self._acctStaticChangeReqResults

    def getAcctOpenCloseResponseResult(self):
        return self._acctOpenCloseRespResults

    def getAcctRejectResponseResult(self):
        return self._acctRejectRespResults

    def getAcctStaticDataChangeResponseResult(self):
        return self._acctStaticChangeRespResults


STARTREK_REPORT_TEMPLATE = \
"""Hi All,
Here is the report on automation from {%TIME_BEGIN%} to {%TIME_END%}
{%REPORT_HIGHLIGHTS_BLOCK%}{%REPORT_HIGHLIGHT_SEPARATOR%}{%CRR1_REPORT_BLOCK%}{%REPORT_SEPARATOR%}{%CR776_REPORT_BLOCK%}
"""

REPORT_HIGHLIGHTS_BLOCK = \
"""
{%REPORT_HIGHTLIGHTS_BLOCK_TITLE%}
{%SYSTEM_STATUS_BLOCK%}

{%CRR1_REPORT_ERRORS_TITLE%}:
{%CRR1_REPORT_ERRORS_CONTENT%}

{%CRR776_REPORT_ERRORS_TITLE%}:
{%CRR776_REPORT_ERRORS_CONTENT%}"""

SYSTEM_STATUS_BLOCK = \
"""
{%SYSTEM_REPORT_TITLE%}:
1. There are {%PARTITION_COUNT%} partitions above {%PARTITION_THRESHOLD_CAPACITY%}% capacity.
{%PARTITION_CAPACITY_REPORT%}
2. The SFTP server is {%SFTP_CONNECTABLE%}.

3. There are {%SFTP_OLD_FILE_COUNT%} unfetched files on the SFTP server older than {%SFTP_OLD_FILE_MIN_AGE_HR%} hour.
{%UNFETCHED_SFTP_FILE_REPORT%}
4. {%CRR1_REPORT_ERRORS_TITLE_MSG%}
{%CRR1_REPORT_ERRORS_CONTENT%}

5. {%CR776_REPORT_ERRORS_TITLE_MSG%}
{%CR776_REPORT_ERRORS_CONTENT%}
"""

CRR1_REPORT_BLOCK = \
"""
{%TITLE%}

1. There were {%PAYEE_COUNT%} payee files and {%PAYMENT_COUNT%} payment files uploaded for processing.
{%UL_FILES_CONTENT%}

2. {%ACKS_REPORT%}


3. The automation have downloaded {%BANSTA_COUNT%} BANSTA files for processing.
{%BANSTA_CONTENT%}

{%EXTRA_MSG%}"""

CR776_REPORT_BLOCK = \
"""
{%TITLE%}

1. There were {%ACCT_OPEN_REQ_COUNT%} acct_open_close, {%ACCT_STATIC_CHANGE_REQ_COUNT%} acct_static_data_change, and {%ACCT_REJECT_REQ_COUNT%} acct_reject Bulkload Request files downloaded.
{%ACCT_REQ_CONTENT%}

2. There were {%ACCT_OPEN_RESP_COUNT%} acct_open_close, {%ACCT_STATIC_CHANGE_RESP_COUNT%} acct_static_data_change, {%ACCT_REJECT_RESP_COUNT%} acct_reject Bulkload Response files uploaded.
{%ACCT_RESP_CONTENT%}"""

class ReportGenerator(object):
    _NL = '\n'
    _HEADER_LINECT_CR776_DL = 1
    _HEADER_LINECT_CR776_UL = 1
    _HEADER_LINECT_CRR1_DL = 0
    _HEADER_LINECT_CRR1_UL = 0

    def __init__(self, summary, doCrR1=True, doCr776=False, \
                 doSystemReport=False, sftpSpec=None, sftpMinFileAge = 1,
                 sftpTimeZone=None, partitionThreshold=None):
        self._summary = summary
        self._report = None
        self._reportCrR1 = doCrR1
        self._reportCr776 = doCr776
        self._reportSystemStatus = doSystemReport

        self._emptyCrR1Report = True
        self._emptyCr776Report = True
        self._emptySystemReport = True

        self._sftpSpec = sftpSpec
        self._sftpTimeZone = sftpTimeZone
        self._partitionThreshold = partitionThreshold
        self._reportErrorLists = {'CRR1':[], 'CR776':[]}
        self._unfetchedFileAgeHr = sftpMinFileAge

    "Is it an empty report"
    def isReportEmpty(self):
        self.genReport()
        ret = (not self._reportCr776 or self._emptyCr776Report) \
                and (not self._reportCrR1 or self._emptyCrR1Report) \
                and (not self._reportSystemStatus or self._emptySystemReport)
        logger.debug("isReportEmpty = %s"%ret)
        return ret

    def genReport(self):
        if self._report:
            return self._report

        timeBegin, timeEnd = self._summary.getProcessedTimeRange()
        timeBeginStr = timeBegin.strftime("%Y-%m-%d %H:%M")
        timeEndStr = timeEnd.strftime("%Y-%m-%d %H:%M")

        ret = self._getReportTemplate()\
        .replace("{%TIME_BEGIN%}", timeBeginStr)\
        .replace("{%TIME_END%}", timeEndStr)\

        #
        if self._reportCrR1 and self._reportCr776:
            ret = ret.replace("{%REPORT_SEPARATOR%}", self._NL+self._NL+self._getReportSeparator()+self._NL)
        else:
            ret = ret.replace("{%REPORT_SEPARATOR%}", "")

        if self._reportCrR1:
            ret = ret.replace( "{%CRR1_REPORT_BLOCK%}", self._genCrR1ReportBlock().strip() )
        else:
            ret = ret.replace( "{%CRR1_REPORT_BLOCK%}", "" )

        if self._reportCr776:
            ret = ret.replace( "{%CR776_REPORT_BLOCK%}", self._genCr776ReportBlock().strip() )
        else:
            ret = ret.replace( "{%CR776_REPORT_BLOCK%}", "" )

        if len(self._reportErrorLists['CRR1']) > 0 \
        or  len(self._reportErrorLists['CR776']) > 0 \
        or self._reportSystemStatus:
            ret = ret.replace("{%REPORT_HIGHLIGHTS_BLOCK%}", self._NL+self._genReportHighlightBlock() )
            ret = ret.replace("{%REPORT_HIGHLIGHT_SEPARATOR%}", self._NL+self._getReportSeparator()+self._NL)
        else:
            ret = ret.replace("{%REPORT_HIGHLIGHTS_BLOCK%}", "")
            ret = ret.replace("{%REPORT_HIGHLIGHT_SEPARATOR%}", "")

        self._report = ret
        return self._report

    def _rstrip(self, content):
        while content.endswith(self._NL):
            content = content[:-1*len(self._NL)]
        return content

    def _genCr776ReportBlock(self):
        getTotalOccurrence = lambda(x):sum([ i.occurNum for i in x ])

        errList = list( self._summary.getCr776ErrorList() )     #clone to modify
        acctOpenReqList = self._summary.getAcctOpenCloseRequestResult()
        acctRejectReqlist = self._summary.getAcctRejectRequestResult()
        acctChangeReqList = self._summary.getAcctStaticDataChangeRequestResult()
        acctOpenRespList = self._summary.getAcctOpenCloseResponseResult()
        acctRejectRespList = self._summary.getAcctRejectResponseResult()
        acctChangeRespList = self._summary.getAcctStaticDataChangeResponseResult()
        reqContent = ""
        respContent = ""

        "populate the request content"
        for reqList in [acctOpenReqList, acctChangeReqList, acctRejectReqlist]:
            for req in reqList:
                reqContent += self._NL + self._getFormattedFileName( req.fileName )
                if req.isInExpectedPath():
                    reqFileLineCt = req.getLineCount() - self._HEADER_LINECT_CR776_DL
                    #Check for zero byte file
                    if req.isFileEmpty():
                        errList.append(ErrorReport("Empty (0byte) CR776 Request File",
                                   "CR776 Request File is empty: %s"%(req.fileName), "") )
                    #Check for zero data row
                    elif reqFileLineCt == 0:
                        errList.append(ErrorReport("CR776 Request File have 0 data rows",
                                   "File have 0 data rows: %s"%(req.fileName), "") )
                        
                    reqContent += ( " [%s data rows] "%(max(0, reqFileLineCt)) )
                if req.occurNum > 1:
                    reqContent += " ( downloaded %d times within report period)"%req.occurNum
            req = None  #resetting to ensure no mis-use by accident

        "populate the response content"
        for respList, formatFunc \
        in [( acctOpenRespList, self._getMaskedAcctOpenCloseResponseContent ),
            ( acctChangeRespList, self._getMaskedAcctStaticDataChangeResponseContent ),
            ( acctRejectRespList, self._getMaskedAcctRejectResponseContent )]:
            for resp in respList:
                formattedName = self._getFormattedFileName( resp.fileName )
                formattedContent = "*Unable to retrieve file content*"
                isErrorResponse = False
                if resp.isInExpectedPath():
                    formattedName += ( " [%s data rows] "%(max(0, resp.getLineCount()-self._HEADER_LINECT_CR776_UL)) )
                    isErrorResponse, formattedContent = formatFunc(resp.expectedPath)
                elif resp.isTransferPending:
                    isErrorResponse, formattedContent = formatFunc(os.path.join( DIR_DL_RESP, resp.fileName ))

                if isErrorResponse:
                    errList.append(ErrorReport("Invalid Bulkload Request File format",
                                   "Request File in invalid format: %s"%(os.path.splitext(resp.fileName)[0]+'.csv'), ""))

                nameExt = []
                if resp.occurNum > 1:
                    nameExt.append( "Last of %d Upload"%resp.occurNum )
                if resp.isTransferPending:
                    nameExt.append( "Pending transfer" )
                if len(nameExt) > 0:
                    formattedName += " ( %s )"%(", ".join(nameExt))

                respContent += self._NL + formattedName
                respContent += self._NL
                respContent += formattedContent + self._NL

        "populate the error message if any"
        if errList:
            self._reportErrorLists['CR776'] = errList

        "sets whether if this is a empty report"
        self._emptyCr776Report = (len( errList ) +len( acctOpenReqList )\
                                   + len( acctRejectReqlist ) + len( acctChangeReqList ) \
                                   + len( acctOpenRespList ) + len( acctRejectRespList ) \
                                   + len( acctChangeRespList )) == 0
        logger.debug("Empty CR776 report = %s"%self._emptyCr776Report)
        return self._getCr776ReportBlockTemplate()\
            .replace("{%TITLE%}", self._getFormattedTitle("CR-776 Automation Summary"))\
            .replace("{%ACCT_OPEN_REQ_COUNT%}" , "%d"%getTotalOccurrence(acctOpenReqList))\
            .replace("{%ACCT_STATIC_CHANGE_REQ_COUNT%}" , "%d"%getTotalOccurrence(acctChangeReqList))\
            .replace("{%ACCT_REJECT_REQ_COUNT%}" , "%d"%getTotalOccurrence(acctRejectReqlist))\
            .replace("{%ACCT_REQ_CONTENT%}" , reqContent)\
            .replace("{%ACCT_OPEN_RESP_COUNT%}" , "%d"%getTotalOccurrence(acctOpenRespList))\
            .replace("{%ACCT_STATIC_CHANGE_RESP_COUNT%}" , "%d"%getTotalOccurrence(acctChangeRespList))\
            .replace("{%ACCT_REJECT_RESP_COUNT%}" , "%d"%getTotalOccurrence(acctRejectRespList))\
            .replace("{%ACCT_RESP_CONTENT%}", respContent)

    def _genCrR1ReportBlock(self):
        errList = self._summary.getCrR1ErrorList()
        payeeList = self._summary.getPayeeFilesResult()
        paymentList = self._summary.getPaymentFilesResult()
        banstaList = self._summary.getBanstaFilesResult()
        extraAcksList = self._summary.getExtraAcksFilesList()

        extraMsg = ""
        if extraAcksList:
            extraMsg = "4. The following additional acks/rejs files were received: %s%s"\
            %(self._NL, self._NL.join([ i.fileName for i in extraAcksList ]))

        if errList:
            self._reportErrorLists['CRR1'] = errList

        self._emptyCrR1Report = ( len(errList) + len(payeeList) + len(paymentList) \
                                  + len(banstaList) + len(extraAcksList)) == 0
        logger.debug("Empty CRR1 report = %s"%self._emptyCrR1Report)
        return self._getCrR1ReportBlockTemplate()\
        .replace("{%TITLE%}", self._getFormattedTitle("CR-R1 Automation Summary"))\
        .replace("{%PAYEE_COUNT%}", "%d" % len(payeeList))\
        .replace("{%PAYMENT_COUNT%}", "%d" % len(paymentList))\
        .replace("{%UL_FILES_CONTENT%}", self._getFormattedUlContent(payeeList, paymentList))\
        .replace("{%ACKS_REPORT%}", self._getFormattedAckContent(payeeList, paymentList))\
        .replace("{%BANSTA_COUNT%}", "%d" % len(banstaList))\
        .replace("{%BANSTA_CONTENT%}", self._getFormattedBanstaContent(banstaList))\
        .replace("{%EXTRA_MSG%}", extraMsg)

    def _genReportHighlightBlock(self):
        msgList = []
        if self._reportSystemStatus:
            self._emptySystemReport = False
            msgList += self._genSystemStatusMessageLists()
        msgList += self._genReportErrorMessageList();
        return self._getFormattedTitle("Report Errors and Alarms") + self._NL + self._genFormattedMsgAsOrderLists(msgList)

    def _genReportErrorMessageList(self):
        crr1ErrorMessage = "No issues were observed for CR-R1."
        cr776ErrorMessage = "No issues were observed for CR-776."

        if len(self._reportErrorLists['CRR1']) > 0:
            crr1ErrorMessage = "There are %s errors found in CR-R1. %s%s"%\
                                (self._getStringAsErrorHighlighted("%s"%len(self._reportErrorLists['CRR1'])), \
                                 self._NL,\
                                 self._genErrorMessages(self._reportErrorLists['CRR1']))
        if len(self._reportErrorLists['CR776']) > 0:
            cr776ErrorMessage = "There are %s errors found in CR-776. %s%s"%\
                                (self._getStringAsErrorHighlighted("%s"%len(self._reportErrorLists['CR776'])), \
                                 self._NL,\
                                 self._genErrorMessages(self._reportErrorLists['CR776']))
        return [crr1ErrorMessage, cr776ErrorMessage]

    def _genSystemStatusMessageLists(self):
        retMsgList = []
        sftpUserName, hostSpec = self._sftpSpec.split("@")
        sftpHost, sftpPort, sftpDir = hostSpec.split(":")
        sftpPort = int(sftpPort)

        #Get all the stats
        sysAnalyzer = SystemStatusAnalyzer();
        overusedPartitions = sysAnalyzer.getMountPointsAboveCapacity(self._partitionThreshold)
        sftpConnectable = sysAnalyzer.isSFtpConnectable(sftpHost, sftpPort, sftpUserName)
        unfetchedFiles = []
        if sftpConnectable:
            unfetchedFiles = sysAnalyzer.getSFtpFileOlderThan(sftpHost, sftpPort, sftpDir, timedelta(hours=self._unfetchedFileAgeHr), sftpUserName, self._sftpTimeZone)

        #Format all of the stats
        txtPartitionCount = self._getStringAsSuccessHighlighted("0")
        txtPartitionThreshold = "%s"%self._partitionThreshold
        txtPartitionReport = ""
        if len(overusedPartitions) > 0:
            txtPartitionCount = self._getStringAsErrorHighlighted("%d"%len(overusedPartitions))
            tmpMsgList = [self._getStringAsErrorHighlighted("Partition: %s , Capacity: %s%%"
                                                            %(i, j))
                          for (i,j) in overusedPartitions]
            txtPartitionReport = self._genFormattedMsgAsUnorderLists(tmpMsgList)
        retMsgList.append("There are %s partitions above %s%% usage capacity. %s%s"%( txtPartitionCount,
                                                                                    txtPartitionThreshold,
                                                                                    txtPartitionReport and self._NL,
                                                                                    txtPartitionReport) )

        txtSftpConnectable = self._getStringAsSuccessHighlighted("connectable")
        if not sftpConnectable:
            txtSftpConnectable = self._getStringAsErrorHighlighted("UNREACHABLE")
        retMsgList.append("The SFTP server is %s."%txtSftpConnectable)

        if sftpConnectable:
            txtSftpUnfetchedFileCount = self._getStringAsSuccessHighlighted("0")
            txtSftpUnfecthedFileReport = ""
            if len(unfetchedFiles) > 0:
                txtSftpUnfetchedFileCount = self._getStringAsErrorHighlighted("%s"%len(unfetchedFiles))
                tmpMsgList = [self._getStringAsErrorHighlighted("File: %s , TimeStamp: %s"
                                                                %(i, j.strftime(FMT_UNFETCHED_FI_TS)))
                              for (i,j) in unfetchedFiles]
                txtSftpUnfecthedFileReport = self._genFormattedMsgAsUnorderLists(tmpMsgList)
            retMsgList.append(("There are %s unfetched files"+\
                              " on the SFTP server older than %s hours. %s%s")\
                              %( txtSftpUnfetchedFileCount,
                                 self._unfetchedFileAgeHr,
                                 txtSftpUnfecthedFileReport and self._NL,
                                 txtSftpUnfecthedFileReport) )
        return retMsgList

    """
    @errList: a list of ErrorReport
    """
    def _genErrorMessages(self, errList):
        #Group all of the errors
        errorMap = {}
        for errReport in errList:
            if not errorMap.has_key(errReport.title):
                errorMap[errReport.title] = []
            errorMap[errReport.title].append(errReport)
        errorTitles = errorMap.keys()
        errorTitles.sort()
        #Generate the message through ordered listing
        ret = ""
        msgLists = []
        for idx, title in enumerate(errorTitles):
            errDescriptions = [ self._getStringAsErrorHighlighted(j.description)
                                for j in errorMap[title] ]
            msgLists.append( title +" : "\
                             + self._NL
                             + self._genFormattedMsgAsUnorderLists(errDescriptions) )
        return self._genFormattedMsgAsAlphaOrderLists( msgLists )

    def _getFormattedAckContent(self, payeeList, paymentList):
        ret = ""
        for pState in payeeList+paymentList:
            if len(pState.responsesRecv) > 1:
                ret += "%s were received for file %s%s" % (", ".join(pState.responsesRecv) , pState.fileName, self._NL)
            elif len(pState.responsesRecv) == 1:
                ret += "An %s was received for file %s%s" % (pState.responsesRecv[0], pState.fileName, self._NL)
            else:
                ret += "No acks or rejs was received for file %s%s" %(pState.fileName, self._NL)
        if not ret:
            ret = "No acks or rejs was received."

        while ret.endswith(self._NL):   #remove whitespace and <br > tags
            ret = ret[:-1*len(self._NL)]
        return ret

    def _genFormattedMsgAsUnorderLists(self, msgLists):
        ret = ""
        for idx, msg in enumerate(msgLists):
            ret += " * %s %s"%(msg, self._NL)
        return self._rstrip(ret)

    def _genFormattedMsgAsOrderLists(self, msgLists):
        ret = ""
        for idx, msg in enumerate(msgLists):
            ret += "%d. %s %s"%(idx+1, msg, self._NL)
        return self._rstrip(ret)

    def _genFormattedMsgAsAlphaOrderLists(self, msgLists):
        ret = ""
        for idx, msg in enumerate(msgLists):
            ret += "%s. %s %s"%(chr(ord('a')+idx), msg, self._NL)
        return self._rstrip(ret)

    "Methods to be implemented."
    def _getReportSeparator(self):
        return "="*80

    def _getFormattedTitle(self, name):
        return name

    def _getFormattedSubtitle(self, name):
        return name

    def _getFormattedFileName(self, name):
        return name

    def _getReportTemplate(self):
        return STARTREK_REPORT_TEMPLATE

    def _getCrR1ReportBlockTemplate(self):
        return CRR1_REPORT_BLOCK

    def _getCr776ReportBlockTemplate(self):
        return CR776_REPORT_BLOCK

    def _getSystemStatusBlockTemplate(self):
        return SYSTEM_STATUS_BLOCK

#     def _getReportErrorsBlockTemplate(self):
#         return REPORT_ERROR_BLOCK

    def _getStringAsErrorHighlighted(self, errStr):
        return errStr

    def _getStringAsSuccessHighlighted(self, succStr):
        return succStr

    "CR-R1"
    def _getFormattedUlContent(self, payeeList, paymentList):
        raise NotImplementedError()

    def _getFormattedBanstaContent(self, banstaList):
        raise NotImplementedError()

    "CR-776"
    def _decorateErrAcctFileContent(self, content):
        return content

    def _getMaskedAcctFile(self, filePath, errorHeader, maskFields):
        fi = open(filePath)
        foundError = False
        header = fi.readline().strip()
        ret = header
        if header == errorHeader:
            foundError = True
            ret += self._NL + self._decorateErrAcctFileContent( fi.read().rstrip() )
            ret.replace("\r\n", "\n").replace("\n", self._NL)
        else:
            for line in fi:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                for idx in maskFields:
                    parts[idx] = "*"*len(parts[idx])    #mask off primary ID
                ret += self._NL +  (",".join(parts))
        return (foundError,ret)

    def _getMaskedAcctOpenCloseResponseContent(self, filePath):
        return self._getMaskedAcctFile(filePath, "STATUS_CODE,STATUS_TEXT", [1,2,3] )

    def _getMaskedAcctRejectResponseContent(self, filePath):
        return self._getMaskedAcctFile(filePath, "STATUS_CODE,STATUS_TEXT", [1] )

    def _getMaskedAcctStaticDataChangeResponseContent(self, filePath):
        return self._getMaskedAcctFile(filePath, "STATUS_CODE,STATUS_TEXT", [0] )

class PlainTextReportGenerator(ReportGenerator):
    def _getFileContent(self, filePath, printRowCount=False, headerCount=0):
        fi = open(filePath)
        try:
            fileContent = fi.read().strip()
            extraNameText = ""
            if printRowCount:
                extraNameText = " [%d data rows] "%max(0, len( fileContent.split('\n')) - headerCount)
            return os.path.basename(filePath) + extraNameText + "\n" + fileContent
        finally:
            fi.close()
    def _getFormattedUlContent(self, payeeList, paymentList):
        return "\n" + \
            ("\n\n".join([ self._getFileContent(i.expectedPath, True, self._HEADER_LINECT_CRR1_UL)
                         for i in payeeList + paymentList ])) + "\n"

    def _getFormattedBanstaContent(self, banstaList):
        return "\n" + \
            ("\n\n".join([ self._getFileContent(i.expectedPath, True, self._HEADER_LINECT_CRR1_DL)
                             for i in banstaList ])) + "\n"

class HtmlReportGenerator(ReportGenerator):
    _BANSTA_DELIMITER = ','
    _NL = '\n<br />'

    def _genFormattedMsgAsUnorderLists(self, msgLists):
        ret = ""
        for msg in msgLists:
            ret += "<li> %s </li> \n"%msg
        return "<ul>%s</ul> \n"%self._rstrip(ret)

    def _genFormattedMsgAsOrderLists(self, msgLists):
        ret = ""
        for msg in msgLists:
            ret += "<li> %s </li> \n"%msg
        return "<ol>%s</ol> \n"%self._rstrip(ret)

    def _genFormattedMsgAsAlphaOrderLists(self, msgLists):
        ret = ""
        for msg in msgLists:
            ret += "<li> %s </li> \n"%msg
        return '<ol type="A">%s</ol> \n'%self._rstrip(ret)

    def _getReportSeparator(self):
        return "<hr />"

    def _getFormattedTitle(self, name):
        return '<span style="font-weight:bold;font-size:13pt;text-decoration:underline">%s</span>'%name

    def _getFormattedSubtitle(self, name):
        return '<span style="font-weight:bold;font-size:11pt;text-decoration:underline">%s</span>'%name

    def _getFormattedFileName(self, name):
        return '<span style="font-weight:bold;">%s</span>' % os.path.basename(name)

    def _getStringAsErrorHighlighted(self, errStr):
        return '<span style="font-weight:bold;color:#FF0000;">%s</span>' %errStr

    def _getStringAsSuccessHighlighted(self, succStr):
        return '<span style="font-weight:bold;color:#00DD00;">%s</span>' %succStr

    def _getReportTemplate(self):
        template = super(HtmlReportGenerator, self)._getReportTemplate()\
        .replace("\r\n", "\n").replace("\n", self._NL)

        return '<html><head></head><body>'+\
               '<span style="font-size:11.0pt;font-family:Calibri,sans-serif;color:#1F497D;">'+\
               template+\
               '</span></body></html>'

    def _getCrR1ReportBlockTemplate(self):
        return super(HtmlReportGenerator, self)._getCrR1ReportBlockTemplate()\
            .replace("\r\n", "\n").replace("\n", self._NL)

    def _getCr776ReportBlockTemplate(self):
        return super(HtmlReportGenerator, self)._getCr776ReportBlockTemplate()\
            .replace("\r\n", "\n").replace("\n", self._NL)

    def _getSystemStatusBlockTemplate(self):
        return super(HtmlReportGenerator, self)._getSystemStatusBlockTemplate()\
            .replace("\r\n", "\n").replace("\n", self._NL)

#     def _getReportErrorsBlockTemplate(self):
#         return super(HtmlReportGenerator, self)._getReportErrorsBlockTemplate()\
#             .replace("\r\n", "\n").replace("\n", self._NL)

    def _getFileContentAsHtml(self, filePath):
        fi = open(filePath)
        try:
            content = fi.read()
            return content.strip().replace("\r\n", "\n").replace("\n", self._NL)
        finally:
            fi.close()

    def _getFormattedUlContent(self, payeeList, paymentList):
        ret = ""
        for pList in (payeeList, paymentList):
            for pState in pList:
                filePath = pState.expectedPath
                ret += self._NL\
                     + self._getFormattedFileName( os.path.basename(filePath) )\
                     + " [%s data rows] "%max(0,( pState.getLineCount() - self._HEADER_LINECT_CRR1_UL)) \
                     + self._NL + self._getFileContentAsHtml(filePath) + self._NL
        return ret

    def _decorateErrAcctFileContent(self, content):
        return r'<span style="background-color:red;">%s</span>'%content

    def _getFormattedBanstaContent(self, banstaList):
        ret = ""
        for bState in banstaList:
            filePath = bState.expectedPath
            fileContent = ""
            fi = open(filePath)
            try:
                lines = fi.readlines()  # header
                fileContent += lines[0].strip()
                for line in lines[1:-1]:
                    lineParts = line.strip().split(self._BANSTA_DELIMITER)
                    lineParts[1] = r'<span style="background-color:yellow;">' + lineParts[1]
                    lineParts[2] + r'</span>'
                    lineParts[2] = lineParts[2] + r'</span>'
                    fileContent += self._NL + (self._BANSTA_DELIMITER.join(lineParts))
                fileContent += self._NL + lines[-1]
            finally:
                fi.close()

            ret += self._NL\
                 + self._getFormattedFileName( os.path.basename(filePath) )\
                 + (" [%s data rows] "%max(0, bState.getLineCount() - self._HEADER_LINECT_CRR1_DL))\
                 + self._NL + fileContent + self._NL
        return ret


def sendSimpleEmail(smtpServer, fromAddr, toAddrs, subject, body,
                    inHtml=False, useTls=False, username=None, pwd=None):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = fromAddr
    msg['To'] = ", ".join(toAddrs)

    msgPart = None
    if inHtml:
        msgPart = MIMEText(body, 'html')
    else:
        msgPart = MIMEText(body, 'plain')

    "NOTE: Uncomment to use base64 encoding. useful if some characters are inserted during transport"
#     encoders.encode_base64(msgPart)                 #encodes into base-64, so the line length never exceeds RFC2822 limitation
#     del msgPart['Content-Transfer-Encoding']        #remove duplicate header
#     msgPart['Content-Transfer-Encoding'] = "base64"

    msg.attach(msgPart)

    server = smtplib.SMTP(smtpServer, timeout=30)
    server.set_debuglevel(1)
    if useTls:
        server.ehlo()
        server.starttls()
        server.login(username, pwd)
    server.sendmail(fromAddr, toAddrs, msg.as_string())
    server.quit()

def isStringEmailList(s):
    return all(map(lambda(x):PAT_EMAIL.match(x.strip()),
                   filter(lambda(x):x.strip(),
                          s.split(","))))
def getArgs():
    def reportArgError(msg):
        logger.error(msg)
        parser.error(msg)  # TODO: probably raise exception instead

    logger.debug("Script is called with args: %s" % str(sys.argv))
    #b,i,e,f,a,r,s,p,t,u,w,o
    parser = OptionParser()
    parser.add_option("-b", "--starttime", dest="startTime", metavar="TIMESTAMP",
                      help="Timestamp to begin search for file transfers. Default is 24 hours before the script call time"\
                      + "TIMESTAMP format: YYYY-MM-DD_hh.mm.ss")
    parser.add_option("-i", "--preceedhours", dest="preceedHours", metavar="POSTIVE_INTEGER",
                      help="Instead of -b, you can use -i to specify the number of hour preceeding the --endtime(default to now) to scan for files")
    parser.add_option("-e", "--emailaddr", dest="toEmailAddrs", metavar="EMAIL_LIST",
                      help="Emails to receive the reports. If this option is used, the -s,-f must be provided as well"\
                      + "EMAIL_LIST format: A double-quoted list of email addresses separated by comma.")
    parser.add_option("-f", "--fromemailaddr", dest="fromEmailAddr", metavar="EMAIL",
                      help="Source email address of the report")
    parser.add_option("-a", "--adminemailaddr", dest="adminEmailAddrs", metavar="EMAIL_LIST",
                      help="Email address to alert to in case of error. -s must be specified when this option is used")
    parser.add_option("-r", "--htmlEmail", dest="htmlEmail", action="store_true", default=False,
                      help="Send rich html email.")
    parser.add_option("-s", "--smtpserver", dest="smtpServer", metavar="IP",
                      help="Hostname/IP Address of the SMTP Server.")
    parser.add_option("-p", "--smtpport", dest="smtpPort", metavar="INT",
                      help="Port of the SMTP Server.")
    parser.add_option("-t", "--useTls", dest="useTls", metavar="BOOL", action="store_true", default=False,
                      help="Use TLS to connect to SMTP server. e.g. Gmail uses it")
    parser.add_option("-u", "--username", dest="username", metavar="STRING",
                      help="Username to connect to SMTP server. e.g. Gmail uses it")
    parser.add_option("-w", "--password", dest="password", metavar="STRING",
                      help="Password to connect to SMTP server. e.g. Gmail uses it")
    parser.add_option("-o", "--output", dest="saveReport", action="store_true", default=False,
                      help="Save the report into the startrek/report/automation folder")
    parser.add_option("--crr1", dest="reportCrR1", action="store_true", default=False,
                      help="Reports CR-R1 automation")
    parser.add_option("--cr776", dest="reportCr776", action="store_true", default=False,
                      help="Reports CR776 automation")
    parser.add_option("--subject", dest="subject", metavar="STRING",
                      help="Change the email subject to")
    parser.add_option("--subjecttimestamp", dest="subjectTimestamp", metavar="STRING", default="%Y-%m-%d",
                      help="Change the email subject's timestamp box. Follow Pythong's datetime.strptime format")
    parser.add_option("--stoponempty", dest="stopOnEmpty", action="store_true", metavar="BOOL", default=False,
                      help="Do not generate any report if there is no file transfers")
    parser.add_option("--reportsystemstatus", dest="reportSystemStatus", action="store_true", metavar="BOOL", default=False,
                      help="Reports on system status")
    parser.add_option("--sftpspec", dest="sftpSpec", metavar="STRING", default=False,
                      help="SFTP link spec of format USERNAME@HOST:PORT:DIR to report ftp info")
    parser.add_option("--sftpfileminage", dest="sftpFileMinAge", metavar="INT", default=1,
                      help="Minimum SFTP file age in hours to report errors on")
    parser.add_option("--partitionthreshold", dest="partitionThreshold", metavar="INT", default=90,
                      help="Partition Capacity Threshold to trigger report")
    parser.add_option("--sftplogfile", dest="sftpLogFile", metavar="FILEPATH", default=LOG_SCBANK_FTP,
                      help="The SFTP File to parse instead of the default. Default is %s"%LOG_SCBANK_FTP)
    parser.add_option("--endtime", dest="endTime", metavar="TIMESTAMP",
                      help="Timestamp to end search for file transfers. Default is now."\
                      + "TIMESTAMP format: YYYY-MM-DD_hh.mm.ss")
    parser.add_option("--sftptimezone", dest="sftpTimeZone", metavar="TIMEZONE", default="UTC",
                       help="Name of timezone in REGION/SUBREGION format, e.g. US/Eastern, Asia/Singapore. "+\
                       "Refer to http://en.wikipedia.org/wiki/List_of_tz_database_time_zones ")
    parser.add_option("--ignorefilepattern", dest="ignoreFilePattern", metavar="REGEX", action="append",
                       help="Matches a regex against a filename found in the sftp log, if match, file will be ignored rather than reported" )
    
    (options, args) = parser.parse_args()
    # Check: argument sanitization checks
    if options.toEmailAddrs:
        if not isStringEmailList(options.toEmailAddrs):
            reportArgError("invalid -e option : %s" % options.toEmailAddrs)
        if not options.fromEmailAddr:
            reportArgError("-f option must be specified when -e is used")
        if not PAT_EMAIL.match(options.fromEmailAddr):
            reportArgError("-f have invalid email address: %s" % options.fromEmailAddr)

    endTime = None
    if not options.endTime:
        endTime = datetime.now()
    else:
        endTime = datetime.strptime(options.endTime, FMT_ARG_TIMESTAMP)

    startTime = None
    if options.startTime and options.preceedHours:
        reportArgError("-i and -b cannot be used together")
    elif options.preceedHours:
        pHours = int(options.preceedHours)
        if pHours <= 0:
            reportArgError("Invalid preceedhours argument: "+pHours)
        startTime = (endTime - timedelta(hours=pHours))
    else:
        if options.startTime and not PAT_TS_ARG.match(options.startTime):
            reportArgError("-b option have invalid timestamp format: %s" % options.startTime)
        if options.startTime:
            startTime = datetime.strptime(options.startTime, FMT_ARG_TIMESTAMP)
        else:
            startTime = (endTime - timedelta(days=1))

    if options.adminEmailAddrs and not isStringEmailList(options.adminEmailAddrs):
        reportArgError("-a option have invalid email address list: %s" % options.adminEmailAddrs)
    if (options.adminEmailAddrs or options.toEmailAddrs) and not options.smtpServer:
        reportArgError("-s option (SMTP Server) must specified when using -e,-a")

    toEmails = []
    adminList = []

    if options.toEmailAddrs:
        toEmails = [ i.strip() for i in options.toEmailAddrs.split(',') if i.strip() ]
    if options.adminEmailAddrs:
        adminList = [ i.strip() for i in options.adminEmailAddrs.split(',') if i.strip() ]

    return (startTime, toEmails, options.fromEmailAddr, adminList, \
            options.htmlEmail, options.smtpServer, options.smtpPort, \
            options.useTls, options.username, options.password, \
            options.saveReport, options.reportCrR1, options.reportCr776, \
            options.subject, options.subjectTimestamp, options.stopOnEmpty, \
            options.reportSystemStatus, options.sftpSpec, int(options.sftpFileMinAge), \
            float(options.partitionThreshold), options.sftpLogFile, endTime, \
            options.sftpTimeZone, options.ignoreFilePattern )

def main():
    try:
        logger.debug("*"*80)
        logger.debug("Process ID: %d, Thread ID: %d"%( os.getpid(), thread.get_ident()))
        if sys.platform != 'win32':
            logger.debug("Parent Process ID: %d "%(os.getppid()))
        startTime, toEmails, fromEmailAddr, adminEmailList, useHtml, \
        smtpServerAddr, smtpPort, useTls, username, pwd, saveReport, \
        reportCrR1, reportCr776, subjectText, subjectTimestamp, stopOnEmpty, \
        reportSystemStatus, sftpSpec, sftpFileMinAge, partitionThreshold, \
        sftpLogFile, endTime, sftpTimeZone, ignoreFilePatternList = getArgs()
        
        if smtpPort:
            smtpServerAddr = smtpServerAddr+":"+smtpPort
        if ignoreFilePatternList:
            for pattStr in ignoreFilePatternList:
                logger.debug("Received ignore pattern %s"%pattStr)
                PAT_IGNORE_FILENAMES.append( re.compile(pattStr) )
        
        processor = AutomationSummaryProcessor(startTime, endTime, sftpLogFile)
        processor.process()

        plainReporter = PlainTextReportGenerator(processor, reportCrR1, reportCr776, reportSystemStatus, sftpSpec, sftpFileMinAge, sftpTimeZone, partitionThreshold)
        htmlReporter = HtmlReportGenerator(processor, reportCrR1, reportCr776, reportSystemStatus, sftpSpec, sftpFileMinAge, sftpTimeZone, partitionThreshold)
        reporter = plainReporter

        if useHtml:
            reporter = htmlReporter

        report = reporter.genReport()

        if reporter.isReportEmpty() and stopOnEmpty:
            logger.debug("Nothing to send in report, terminating by --stoponempty flag.")
            return

        logger.info("\n\nReport on files processed by the RuleEngine from %s to %s :" % (startTime, endTime))
        logger.info("\n"\
                     + "="*80 + "\n"\
                     + report + "\n"\
                     + "="*80)

        if saveReport:
            fileName = "Startrek_daily_automation_report_%s"%(endTime.strftime("%Y-%m-%d_%H.%M.%S"))
            saveDir = os.path.join( DIR_BASE, "reports", "automation")
            if not os.path.exists(saveDir):
                os.makedirs(saveDir)
            for ext,reporter in (('.txt', plainReporter),('.html', htmlReporter)):
                savePath = os.path.join( saveDir, fileName+ext )
                fi = open( savePath, 'w')
                try:
                    fi.write(reporter.genReport())
                finally:
                    fi.close()

        if toEmails:
            subject = "Startrek daily automation report"
            if subjectText:
                subject = subjectText
            subject += " [%s]"%(endTime.strftime(subjectTimestamp))
            sendSimpleEmail(smtpServerAddr, fromEmailAddr, toEmails, subject, report, useHtml, username, pwd)
    except Exception, e:
        logger.exception(e)
        try:
            if adminEmailList:
                stackTrace = traceback.format_exc()
                subject = "Error when generating Startrek daily automation report at %s"%endTime
                body = "Called arguments: " + str(sys.argv) + "\n\n"+ stackTrace
                sendSimpleEmail(smtpServerAddr, "noreply@telepin.com",
                         adminEmailList, subject, body, False, username, pwd)
        except Exception, e2:
            try:
                logger.error("Encountered exception when trying to send alert email.")
                logger.exception(e2)
            except:
                pass
        sys.exit(-1)
    finally:
        logger.info("\n\n\n\n")

def initLogger():
    global logger
    logging.basicConfig(format=FORMAT_LOGGING)
    logFormatter = logging.Formatter(FORMAT_LOGGING)

    logFileHandler = logging.FileHandler(LOG_EXECUTION)
    logFileHandler.setFormatter(logFormatter)
    logFileHandler.setLevel(logging.DEBUG)

    logger = logging.getLogger('scbank_log_report')
    logger.addHandler(logFileHandler)
    logger.setLevel(logging.DEBUG)
    logging.basicConfig()

if __name__ == "__main__":
    initLogger()
    main()