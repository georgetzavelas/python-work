#!/bin/python
import os
import re
import datetime
import sys

HEADER_DATE=re.compile( "^AAA,date,(.+)$" )
HEADER_TIME=re.compile("^AAA,time,(.+)$")
HEADER_SNAPSHOTS=re.compile("^AAA,snapshots,(.+)$")
HEADER_INTERVALS=re.compile("^AAA,interval,(.+)$")

DATA_START_CPU = re.compile("^CPU_ALL,")
DATA_START_MEM = re.compile("^MEM,")
DATA_START_NET = re.compile("^NET,")

COL_IF_READ = re.compile(".*-read-KB/s")
COL_IF_WRITE = re.compile(".*-write-KB/s")


cpuKeyCols = ["Idle%"]
memKeyCols = ["memtotal", "memfree"]

def saveDataBySummingGroups( rowData, patList, nameList, outFileName,  startDateTimeObj, interval ):
  header = rowData[0].split(',')
  groupInds = [[] for i in patList]
  for idx,fieldName in enumerate(header):
    for patIdx,pat in enumerate(patList):
      if pat.search(fieldName):
        groupInds[patIdx].append(idx)
        break

  fi = open(outFileName, 'w')
  fi.write("Name,Time,%s\n"%(",".join(nameList)))
  for line in rowData[1:]:
    parts = line.strip().split(",")
    name = parts[0]
    tsIdx = int(parts[1][1:])
    ts = startDateTimeObj + datetime.timedelta(seconds=(tsIdx-1)*interval)

    aggregates = [ 0.0 for i in groupInds ]
    for groupIdx,groupIdxSet in enumerate(groupInds):
      for idx in groupIdxSet:
        aggregates[groupIdx] += float( parts[ idx] )

    fi.write("%s,%s,%s\n"%(name,ts.strftime("%Y-%m-%dT%H:%M:%S"), ",".join( [str(i) for i in aggregates] )))
  fi.close();



def saveKeyColumns( rowData, keyCols, outFileName, startDateTimeObj, interval ):
  header = rowData[0].split(',')
  colsIdx = [ header.index(i) for i in keyCols ]

  fi = open(outFileName, 'w')
  fi.write("Name,Time,%s\n"%(",".join(keyCols)))
  for line in rowData[1:]:
    parts = line.split(',')
    name = parts[0]
    tsIdx = int(parts[1][1:])
    ts = startDateTimeObj + datetime.timedelta(seconds=(tsIdx-1)*interval)

    fi.write("%s,%s,%s\n"%(name, ts.strftime("%Y-%m-%dT%H:%M:%S"), ",".join([parts[i] for i in colsIdx ])))
  fi.close()


def main():
  if len(sys.argv) < 2 or sys.argv[1] == "":
    print("Usage: script nmon_file_name");
    return

  inputFile = sys.argv[1]
  inputDir = os.path.dirname(inputFile)

  cpuData = []
  memData = []
  netData = []

  startDate = None
  startTime = None
  captureInterval = None
  captureCount = None

  fi = open( inputFile )
  for line in fi:
    line = line.strip();

    matchDate = HEADER_DATE.match(line);
    matchTime = HEADER_TIME.match(line);
    matchSnapshot = HEADER_SNAPSHOTS.match(line);
    matchInterval = HEADER_INTERVALS.match(line);

    matchDataCpu = DATA_START_CPU.match(line);
    matchDataMem = DATA_START_MEM.match(line);
    matchDataNet = DATA_START_NET.match(line);

    if not startDate and matchDate:
      startDate = matchDate.group(1);
      continue

    if not startTime and matchTime:
      startTime = matchTime.group(1);
      continue

    if not captureInterval and matchInterval:
      captureInterval = int(matchInterval.group(1))
      continue

    if not captureCount and matchSnapshot:
      captureCount = int(matchSnapshot.group(1))
      continue

    for storage,match in ((cpuData,matchDataCpu),(memData,matchDataMem),(netData,matchDataNet)):
      if match:
        storage.append(line);
        continue

  fi.close()
  #finished reading data

  cpuData.sort()
  memData.sort()
  netData.sort()

  startDateTime = datetime.datetime.strptime( startDate+" "+startTime, "%d-%b-%Y %H:%M.%S" )
  fileTsComp = startDateTime.strftime("%Y%m%d%H%M%S")

  if "total-read" in netData[0] or "total-write" in netData[0]:
    raise Exception("Contact Dev, total-read/write found on net data");

  saveKeyColumns( cpuData, cpuKeyCols, os.path.join(inputDir, "CPU_%s.csv"%fileTsComp), startDateTime, captureInterval )
  saveKeyColumns( memData, memKeyCols, os.path.join(inputDir, "MEM_%s.csv"%fileTsComp), startDateTime, captureInterval )

  saveDataBySummingGroups( netData, [ COL_IF_READ, COL_IF_WRITE ], ["Total Read(KB/S)", "Total Write(KB/S)"], os.path.join(inputDir, "NET_%s.csv"%fileTsComp),  startDateTime, captureInterval )




if __name__ == "__main__":
  main();
