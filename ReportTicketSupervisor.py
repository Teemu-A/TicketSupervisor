#!/usr/bin/python
""" Reporting for Ticket Supervisor, "Paavo"
    that 
    - reads the log files produced by Paavo
    - summarizes by week/month
    - reports as human-readable or CSV

* Prerequisites
    python (preferably v3)

* For windows exe build
    pip install pyinstaller
    pyinstaller --onefile ReportTicketSupervisor.py

* Use: ReportTicketSupervisor [--csv] [--log_dir directory]

"""
############################################################################################
import argparse, sys, os, glob, datetime, re
from collections import Counter
VERSION="0.1.0"
mpfx="RPT"                                           # Mesage prefix
csv=False                                            # If True, outputs as CSV
log_dir="."                                          # Directory containing the log files
appname="Paavo"                                      # Name of robot application
############################################################################################
def prtmsg(txt,mid="000",msuf="I"):
    '''Print a message to the console. Include a message prefix and timestamp'''
    logstr="{}{}{} {} {}".format(mpfx,mid,msuf,datetime.datetime.now().strftime('%d-%H%M%S'),txt)
    print(logstr)

def OutputFormat():
    if csv:
        return ';"{}";{}'
    return "{:48s}\t{:8d}"

def ReportTicketSupervisor(log_dir):
    '''Process log files found on the directory.'''
    cd=Counter()
    ck=Counter()
    mask=os.path.join(log_dir,"actions-{}-2*.log".format(appname))
    for filen in glob.glob(mask):
        yyyymmdd=filen.split("-")[2].split(".")[0]
        day=datetime.datetime.strptime(yyyymmdd, '%Y%m%d')
        num_match=open(filen, 'r').read().count("PVE202I")
        cd.update(
            {"{}".format(day.strftime("%Y-%m-%d")): num_match
            ,"vko_{}".format(day.strftime("%Y/%W")): num_match
            ,"kuu_{}".format(day.strftime("%Y-%m")): num_match
        })
        _=[ ck.update({line.split(" ")[4]: 1}) for line in open(filen, 'r').read().split("\n") if re.search("PVE202I",line) ]

    for key in sorted(cd.keys()):
        prtmsg(OutputFormat().format(key, cd[key]),mid="10-time-")
    for key in sorted(ck.keys()):
        prtmsg(OutputFormat().format(key, ck[key]),mid="20-rule-")
    prtmsg(OutputFormat().format("*YHT",sum(ck.values())),mid="90-totl-")
############################################################################################
if __name__ == '__main__':
    try:
        me=os.path.basename(sys.argv[0])
        if "--version" in sys.argv:
            prtmsg("Version: {} - {}".format(VERSION,me))
            sys.exit()
        parser=argparse.ArgumentParser(description='Reporter for Personal Assistant for ServiceNow Tickets.')
        parser.add_argument("--appname", help="Name of virtual assistant", action="store", dest="appname", default="Paavo")
        parser.add_argument("--csv", help="Output as CSV", action="store_true", dest="csv")
        parser.add_argument("--log_dir", help="Directory containing log files", action="store", dest="log_dir", default=".")
        runa=parser.parse_args(sys.argv[1:])
        appname=runa.appname
        log_dir=runa.log_dir
        csv=runa.csv
        ReportTicketSupervisor(log_dir)
    except Exception as e:
        prtmsg("Oops. Something went wrong, {} on sick leave, DG: {}".format(appname,str(e)),"091","E")
