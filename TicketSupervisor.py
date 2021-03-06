#!/usr/bin/python
""" Ticket Supervisor, "Paavo"
    that 
    - polls in a 20-sec interval loop (unless started as --once)
    - reads active unassigned tickets from ServiceNow
    - and applies matching actions from yaml file
    - writing log of the actions performed

* Prerequisites
    python (preferably v3)
    pip install pyyaml,pysnow

* For windows exe build
    pip install pyinstaller pywin32
    pip install python-magic-bin==0.4.14
    pyinstaller --clean --noconfirm --onefile TicketSupervisor.py

* Use: TicketSupervisor.py -s "[snc_instance]" -u "[snc_userid]" -p "[snc_password]" [--debug] [--simulate] [--once]
  ... or use the cfg file (desc below) to specify the things

* TicketSupervisor.cfg format:
  global:
    snc: snc_instance_abbrev                    # 1st qualifier of SNC service name
    user: snc_userid                            # Authorized SNC user id
    pwd: snc_password
    appname: ["Paavo","Sirkku"]                 # name of the robot
    proxy: http://your-proxy-name:8080          # In case proxy needed to connect
    cfg_dir: .                                  # Directory where ticket rule cfg is loacted ([appname].txt)
    log_dir: .                                  # If exists, will log into "actions-[appname].YYYYMMDD.log" there
    sleep_sec_between: 20                       # Wait time between loops, unless --once
    first_match_only: True                      # On True, stops scanning rules after 1st match
    ext_cmd_timeout: 30                         # Stop external script/program after 30 seconds
    max_retry_connect: 15                       # Max number of consequent connection errors tolerated
    value_round_robin: False                    # use round-robin to pick values from list
  Paavo:                                       ## Cfg entries overriding global ones for "Paavo"
    snc_state_ignore: "6"                       # Status(es) to ignore on fetching tickets
    snc_table: "incident"                       # Name of SNC table to work on
    snc_assign_group: "[sys_id]"                # Optional, process tickets on this group only
    snc_comment_field: "work_notes"             # can also be "comments"
    snc_shw_descr: "short_description"          # the field to show e.g. no debug messages
  Sirkku:                                      ## Cfg entries overriding global ones for "Sirkku"
    snc_table: "sc_task"
    snc_shw_descr: "u_short_description"
    snc_state_ignore: ["9","10"]
    snc_assign_group: ["z111222333","aaaabbbbcccc"]
    msg_prefix: SKU                             # Message prefix for output log

* Additional variables from *.vars ([robot]-vars-*.txt or Global-vars-*.txt):
- vars:
    key: value

* [appname].yaml format:

- name: [name_of_rule]
  find:                                       (when all match, action(s) are performed)
  - [snc_field]: "[contains_text]"
  - [snc_field]: "^[does_not_contain_text]"
  - [snc_field]: "~[contains_regexp]"
  - [snc_field]: "*[another_snc_field]"
  - [snc_field]: "=[exact full value]"           # assigned_to: "="               = not assigned to anyone
  - [snc_field]: "@[datetime] [arithmetics]"     # updated_at:  "^@now - 12h30m"  = not between now and offset
  - [snc_field]: "^~{variable}"                  # snc_field, env_var, or vars file keyword as exclusive regexp
  act:                                        (list of actions)
  - nop
  - update:
      [snc_field]: "[new_value]"
      [snc_field]: "[new_data] {snc_field} {env_var} [new_data]"
      [snc_field]: ["[value1]","[value2]"]       # Pick randomly a value from the list
  - run1:
      cmd: "command {snc_field} {env_var} {tkt_json_file}"
      [snc_field]: "[new_data] {snc_field} {env_var} [new_data]"

License: MIT

20200325: cfg['global'].get('snc_shw_descr','short_description') to support sctask u_short_description
20200408: v2.0 with support for multiple robots / task types
20200527: v2.1 with optional round-robin value picker from list
20210630: v2.2 adjust cfg scoping on SNC setup
"""
############################################################################################
import yaml, pysnow, requests, argparse, os, sys, platform, json, time, re, tempfile, subprocess, glob, random, copy
from datetime import timedelta,datetime
from requests.exceptions import ConnectionError
VERSION="2.2.0"
mpfx0="RBT"                                          # Default message prefix
mpfx="RBT"                                           # Current message prefix
appname="Paavo"                                      # Name of current robot, used for rule file and output
robotname="Paavo"
debug=False                                          # If True, writes verbosely
quiet=False                                          # If True, shows only matching tickets
simulation=False                                     # If True, does not perform actions
whole_cfg={'global': {'dummy': 'null'}}
log_dir=""                                           # If has a value, writes log
regex_timedelta = re.compile(r'^((?P<days>[\.\d]+?)d)?((?P<hours>[\.\d]+?)h)?((?P<minutes>[\.\d]+?)m)?((?P<seconds>[\.\d]+?)s)?$')
############################################################################################
def prtmsg(txt,mid="000",msuf="I"):
    '''Print a message to the console. Include a message prefix and timestamp'''
    logstr="{}{}{} {} {}".format(mpfx,mid,msuf,datetime.now().strftime('%d-%H%M%S'),txt)
    if log_dir:                                       # Output to file as well if log_dir on cfg
        with open(os.path.join(log_dir,"actions-{}-{}.log".format(robotname,datetime.now().strftime('%Y%m%d'))),"a") as logf:
            logf.write("{}\n".format(logstr))
    print(logstr)

def dbgmsg(txt,mid="800",msuf="D"):
    '''Print a message in case we have debugging on'''
    if debug:
        prtmsg(txt,mid,msuf)

def parse_time(time_str):
    """
    Parse a time string e.g. (2h13m) into a timedelta object.
    :param time_str: A string identifying a duration.  (eg. 2h13m)
    :return datetime.timedelta: A datetime.timedelta object
    """
    parts = regex_timedelta.match(time_str)
    assert parts is not None, "Could not parse any time information from '{}'.  Examples of valid strings: '8h', '2d8h5m20s', '2m4s'".format(time_str)
    time_params = {name: float(param) for name, param in parts.groupdict().items() if param}
    return timedelta(**time_params)

def SelectSingleValue(val,robotname,key,cfg):              # Picks a value to use
    """
    Picks a value to use on updating a field.
    :param val: "test1" , ["value1","value2","value3"], {VARIABLE}
    :note:: uses cfg:value_round_robin selection strategy (random or round robin)
    :return str: single string to use
    """
    if type(val) is not list:                              # For single item,
        return val                                         # ... use it
    if cfg.get('value_round_robin',False):                 # Use round robin?
        ix=0                                               # ... determine which one to use next
        statefile=GetCfgFileName("z_state_{}".format(robotname))
        states={}
        try:
            if os.path.isfile(statefile):
                states=ReadCfg(statefile)                  # read current ix values
        except Exception as e:
            prtmsg("{} {} ?!? {}".format(robotname,key,e),"084","W")
        pick1=states.get(key,-1)+1                         # default=0, else +1
        if pick1>=len(val):                                # if beyond
            pick1=0                                        # ... start over
        states[key]=pick1
        try:
            with open(statefile,'w') as save_state:        # store the current value to file
                yaml.dump(states,save_state,default_flow_style=False)
        except Exception as e:
            prtmsg("{} {} ?!? {}".format(robotname,key,e),"085","W")
        use1=val[pick1]
        dbgmsg("{} <- {}".format(use1,val),"083")          # and use it this round
    else:                                                  # no round robin, pick random
        use1=random.choice(val)                            # pick randomly one value from the list
        dbgmsg("{} <- {}".format(use1,val),"082")          # and use it this round
    return use1

def GetSubArgs(robotname,cfg):
    '''Build a dict of values eligible for substitution; using global vars and *-vars-*.txt files.
       In case of values with lists, pick one random value from the list.
    '''
    dta={}
    masks=[os.path.join(cfg.get('cfg_dir',"."),"{}-vars-*.txt".format(robotname))
        ,os.path.join(cfg.get('cfg_dir',"."),"Global-vars-*.txt")]
    for mask in masks:
        for filen in glob.glob(mask):          # Read in all vars files
            dbgmsg("Vars @ {}".format(filen),"181")
            dta.update(yaml.load(open(filen,'r'),Loader=yaml.Loader))
    dta.update(os.environ)                     # ...and add ENV vars
    dbgmsg("Vars: {}".format(dta),"182")
    return dta

def CmdResultOutput(num,btes,mid):
    '''Print response of an external command'''
    if btes is None:
        return ""
    txt=btes.decode('utf-8')
    for line in txt.replace('\r','').split('\n'):
        if line:
            prtmsg("#{} -> ... {}".format(num,line),mid)

def ReadCfg(cfgfile):
    '''Read the configuration file, done on each 10sec main loop'''
    ymlcfg=yaml.load(open(cfgfile,'r'),Loader=yaml.Loader)
    return ymlcfg

def GetUserName():
    '''Figure out running user name from selected env vars'''
    for varname in ['USERNAME','LOGNAME']:
        if varname in os.environ:
            return os.environ[varname]

def GetCfgFileName(robotname):
    return os.path.join(cfg.get('cfg_dir',"."),"{}.txt".format(robotname))

def EffectiveCfgForOneRobot(robotname):
    '''Append robot specific to global cfg and return'''
    cfg1={}
    for rob1 in ["global",robotname]:       # Pick sections to active cfg for this robot
        if rob1 in whole_cfg:
            for key, value in whole_cfg[rob1].items():
                cfg1[key]=value
    return cfg1
############################################################################################
def SncConnection(snc,user,pwd):
    '''Establish a connection to ServiceNow'''
    s=requests.Session()
    prx=cfg.get('proxy','')
    if prx:
        dbgmsg("Using proxy: {}".format(prx),"183")
        s.proxies.update({'https': prx})
    s.auth=requests.auth.HTTPBasicAuth(user,pwd)
    return pysnow.Client(instance=snc,session=s)

def SncResource(sncclient,snctable):
    return sncclient.resource(api_path='/table/{}'.format(snctable))

def ReadQualifyingTickets(sco,cfg):
    '''Read from ServiceNow, return the result or raise an exception.'''
    qb=pysnow.QueryBuilder().field('active').equals("1")
    if cfg.get('snc_state_ignore',"6"):
        qb.AND().field('state').not_equals(cfg.get('snc_state_ignore',"6"))
    if cfg.get('snc_assign_group',""):
        qb.AND().field('assignment_group').equals(cfg.get('snc_assign_group',""))
    qb.AND().field("sysparm_limit").equals("333")
    dbgmsg("Q: {}".format(qb),"184")
    return sco.get(query=qb).all()

def TicketMatchesRule(num,tkt,rulename,match,subargs):
    '''Compare the values of ticket to single configuration entry. Return True if the ticket matches the criteria.'''
    try:
        runargs=dict(tkt)            # Build a dict of all possible variables to substitute
        runargs.update(subargs)      # (ticket, ENV and *vars*txt)
        for keypair in match:
            return_reverse=False
            for key,val in keypair.items():
                val1="{}".format(val)
                val2="{}".format(tkt[key])
                try:                                           # Substitute variables
                    val1=val1.format(**runargs)
                except Exception:
                    pass
                cmtcc=""
                if bool(len(val1)) and val1[0] == '^':         # e.g. "^Foo"
                    return_reverse=True
                    cmtcc=val1[:1]
                    val1=val1[1:]
                use_regex=False
                use_equals=False
                use_btw=False
                if bool(len(val1)) and val1[0] == "~":         # e.g. "~Foo|Bar" (regexp)
                    use_regex=True
                    val1=val1[1:]
                elif bool(len(val1)) and val1[0] == "=":       # e.g. "=Foo" (exact value)
                    use_equals=True
                    val1=val1[1:]
                elif bool(len(val1)) and val1[0] == "@":       # e.g. "@now - 24h" (between time)
                    use_btw=True
                    btw_attrs=val1[1:].split(" ")
                    base=btw_attrs[0]                          # base to be str YYYY-MM-DD HH:MM:SS
                    if base=="now":
                        base=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    elif bool(len(base)) and base[0] == "*":
                        base="{}".format(tkt[val1[1:]])        # from a field on the ticket
                    ts_1=datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
                    if btw_attrs[1] == "-":
                        ts_2=ts_1
                        ts_1=ts_2-parse_time(btw_attrs[2])
                    else:
                        ts_2=ts_1+parse_time(btw_attrs[2])
                    val1=str(ts_1)
                    val1b=str(ts_2)
                if bool(len(val1)) and val1[0] == '*':         # e.g. "*sys_created_by", "^*sys_updated_at"
                    val1="{}".format(tkt[val1[1:]])
                else:
                    val2="{}".format(tkt[key])
                if cfg.get('ignore_case',False):               # Force lower case to compare
                    val1=val1.lower()
                    val2=val2.lower()
                val1=val1.replace('\n',' ').replace('\r','')   # Replace newlines with blanks before comparing strings
                val2=val2.replace('\n',' ').replace('\r','')
                cstr="{}'{}' {}~ '{}'".format(key[0:35],val2[0:35],cmtcc,val1[0:35])
                if use_regex:
                    matched=bool(re.search(val1,val2)) ^ return_reverse
                elif use_equals:
                    matched=bool(val1==val2) ^ return_reverse
                    cstr="{}'{}' {}= '{}'".format(key[0:35],val2[0:35],cmtcc,val1[0:35])
                elif use_btw:
                    matched=bool(val1<=val2 and val1b>=val2) ^ return_reverse
                    cstr="{} {}[{} ... {}]".format(val2,cmtcc,val1,val1b)
                else:
                    matched=bool(val1 in val2) ^ return_reverse
                dbgmsg("? {}: {}".format(matched,cstr),"382")
                if not matched:                                # Break after first mismatch
                   return False
        return True                                            # All matched
    except Exception as e:
        prtmsg("#{} ?!? {}".format(num,e),"391","W")
        print(e)
        return False                                           # In case of any error, treat as no match

def UpdateTicket(sco,num,dta):
    '''Update a ticket with specfied values (unless --simulation)'''
    if simulation:
        return "[simulation] {}".format(dta)
    return sco.update(query={'number': num},payload=dta)

def ActionsOnTicket(num,rname,tkt,acts,subargs,sco,cfg):
    '''Perform the wished actons on a matching ticket.'''
    for act1 in acts:
        runargs=dict(tkt)            # Build a dict of all possible variables to substitute
        runargs.update(subargs)      # (ticket, ENV and *vars*txt)
        dbgmsg("> {}".format(act1),"481")
        prm=""
        if isinstance(act1,dict):
            prm=list(act1.values())[0]
            act1=list(act1.keys())[0]
        if prm is None:
            prm=""
        if act1 == "nop":
            prtmsg("#{} -> {}".format(num,act1),"401")
        elif act1 == "update":
            fld_comment=cfg.get('snc_comment_field','work_notes')    # comments / work notes
            if fld_comment not in prm:                # Force adding a comment in all cases; default already pretty good
                prm[fld_comment]="{}402I {} -> {}".format(mpfx,robotname,rname)
            for key,val in prm.items():    # Substitute variables, e.g. {number}
                try:
                    prm[key]=SelectSingleValue(val,rname,key,cfg).format(**runargs)      # Pick value & substitute value
                    if prm[key][0]=='[' and prm[key][-1]==']':                           # Got a list? Pick single value
                        prm[key]=str(SelectSingleValue(eval(prm[key]),rname,key,cfg))
                except KeyError:
                    pass
            rsp=UpdateTicket(sco,num,prm)
            prtmsg("#{} -> {}: '{}' -> {}".format(num,act1,prm,rsp),"402")
        elif act1 == "run1":
            tfd, tfile = tempfile.mkstemp()
            try:
                with os.fdopen(tfd,'w',encoding='utf-8') as tmp:       # Write ticket details to a temp file
                    tmp.write(str(eval(json.dumps(tkt))))              # Ugly fix of unicode strings
                runargs['tkt_json_file']=tfile
                run1cmd=prm['cmd'].format(**runargs)
                if simulation:
                   prtmsg("#{} -> [simulation]: '{}'".format(num,run1cmd),"403")
                else:
                   subcmd=subprocess.Popen(run1cmd,stdout=subprocess.PIPE,shell=True)
                   (subcmd_out,subcmd_err)=subcmd.communicate(timeout=int(cfg.get('ext_cmd_timeout',30)))
                   subcmd_status=subcmd.wait()
                   prtmsg("#{} -> {}: RC={} '{}'".format(num,act1,subcmd_status,run1cmd),"403")
                   CmdResultOutput(num,subcmd_err,"404")
                   CmdResultOutput(num,subcmd_out,"405")
            finally:
                os.remove(tfile)
        else:
            prtmsg("#{} ?? {} {}".format(num,act1,prm),"491","E")
    return True

def ProcessSingleTicket(num,tkt,rules,subargs,cfg,sco):
    '''For given ticket, find matching rule(s) and execute actions from them. Return true if something was done.'''
    actions=False
    for rle in copy.deepcopy(rules):   # Use my own copy of rules, as they may have varying variable substitutions
        rname=rle["name"]
        dbgmsg("#{} {}:".format(num,rname),"282")
        if TicketMatchesRule(num,tkt,rname,rle["find"],subargs):
            prtmsg("#{} == {} - {}".format(num,rname,tkt[cfg.get('snc_shw_descr','short_description')][0:127]),"202")
            actions=ActionsOnTicket(num,rname,tkt,rle["act"],subargs,sco,cfg)
            if cfg.get('first_match_only',False):
                return actions
    if not actions and not quiet:
        prtmsg("#{} NA - {}".format(num,tkt[cfg.get('snc_shw_descr','short_description')][0:127]),"201")
    return actions

def LoopRobotsOnce(scli):
    '''Process open tickets once for all robots.'''
    global robotname
    for robotname in appname:
        cfg=EffectiveCfgForOneRobot(robotname)
        global mpfx
        mpfx=cfg.get('msg_prefix',mpfx0)
        sco=SncResource(scli,cfg.get('snc_table','incident'))
        tkts=ReadQualifyingTickets(sco,cfg)
        if tkts:
            try:
                rules=ReadCfg(GetCfgFileName(robotname))
                subargs=GetSubArgs(robotname,cfg)
                dbgmsg("{} n={}, {}".format(robotname,len(tkts),rules),"281")
                for tkt in tkts:
                    num=tkt["number"]
                    try:
                        ProcessSingleTicket(num,tkt,rules,subargs,cfg,sco)
                    except Exception as e:
                        prtmsg("#{} - unsuccessful, {} trying to continue, DG: {}".format(num,robotname,str(e)),"192","E")
            except Exception as e:
                prtmsg("Failed, {} tries to continue, DG: {}".format(robotname,str(e)),"191","E")
        mpfx=mpfx0

def TicketSupervisor(scli):
    '''Main routine for the supervisor. Build a cfg, enter target + credentials and start running'''
    prtmsg("Initialized by {} at {}, v{}, {} awake, starting to work at SNC {}. To stop, Ctrl-C or close the window.".format(GetUserName(),platform.node(),VERSION,appname,snc),"008")
    errRetryCount=0
    for robotname in appname:                                       ### Show configuration file(s)
        cfg=EffectiveCfgForOneRobot(robotname)
        for rle in ReadCfg(GetCfgFileName(robotname)):
            dbgmsg("{}/{} cfg: {}".format(me,robotname,rle),"001")
        sco=SncResource(scli,cfg.get('snc_table','incident'))
        prtmsg("... right now, {} eligible {} tickets for {}.".format(len(ReadQualifyingTickets(sco,cfg)),cfg.get('snc_table','incident'),robotname),"009")

    while True:
        try:
            LoopRobotsOnce(scli)
            errRetryCount=0
        except ConnectionError as e:
            errRetryCount+=1
            maxRetryCount=whole_cfg['global'].get('max_retry_connect',15)
            if errRetryCount <= maxRetryCount:
                prtmsg("Retrying (#{}/{}) a challenging connection in a while - {}".format(errRetryCount,maxRetryCount,type(e)),"092","W")
                time.sleep(30)
            else:
                prtmsg("Terminating due continuing connection trouble","092","E")
                raise e
        time.sleep(whole_cfg['global'].get('sleep_sec_between',20))
############################################################################################
if __name__ == '__main__':
    try:
        me=os.path.basename(sys.argv[0])
        if "--version" in sys.argv:
            prtmsg("Version: {} - {}".format(VERSION,me))
            sys.exit()
        cfgfn="TicketSupervisor.cfg"
        if os.path.isfile(cfgfn):                                            ### Fetch .cfg
            whole_cfg=yaml.load(open(cfgfn,'r'),Loader=yaml.Loader)
        log_dir=whole_cfg['global'].get('log_dir','')
        parser=argparse.ArgumentParser(description='Personal Assistant for ServiceNow Tickets. Performs actions against arrived matching tickets. Configuration on [appname].txt, run args on TiecketSupervisor.cfg')
        snc=whole_cfg['global'].get('snc','')
        parser.add_argument("-s", "--servicenow", help="The name of the ServiceNow system", action="store", default=snc, type=str, required=bool(not snc))
        user=whole_cfg['global'].get('user','')
        parser.add_argument("-u", "--username", help="Username to connect ServiceNow system", action="store", default=user, type=str, required=bool(not user))
        pwd=whole_cfg['global'].get('pwd','')
        parser.add_argument("-p", "--password", help="Password related to username", action="store", default=pwd, type=str, required=bool(not pwd))
        parser.add_argument("--debug", help="Generate additional diagnostic messages", action="store_true", dest="debug")
        parser.add_argument("--simulate", help="Read-only, perform no changes to tickets", action="store_true", dest="simulate")
        parser.add_argument("--once", help="Run just once, not on continuous loop", action="store_true", dest="once")
        parser.add_argument("--quiet", help="Be less verbose", action="store_true", dest="quiet")
        parser.add_argument("--appname", help="Name of virtual assistant", action="store", dest="appname", default=whole_cfg['global'].get('appname',appname), type=str)
        parser.add_argument("--show1", help="Show all attributes of the ticket, value=INCnnnnnnn", action="store", dest="show1", default="", type=str)
        runa=parser.parse_args(sys.argv[1:])
        debug=runa.debug
        quiet=runa.quiet
        simulation=runa.simulate
        appname=runa.appname
        if type(appname) is str:
            appname=[appname]
        snc=runa.servicenow
        user=runa.username
        pwd=runa.password
        cfg=EffectiveCfgForOneRobot(appname[0])
        cfgfile=GetCfgFileName(appname[0])
        scli=SncConnection(snc,user,pwd)
        if runa.show1:                       ##################################################### Show contents of a ticket (e.g. to see field names and values)
            sco=SncResource(scli,'incident')
            for tkt in sco.get(query=(pysnow.QueryBuilder().field('number').equals(runa.show1))).all():
                print(json.dumps(tkt,indent=4,sort_keys=True))
        elif runa.once:                      ##################################################### Run single time
            LoopRobotsOnce(scli)
        else:                                ##################################################### Run as daemon, looping every n+1 seconds
            TicketSupervisor(scli)
    except Exception as e:
        prtmsg("Oops. Something went wrong ({}), {} on sick leave, DG: {}".format(type(e),appname,str(e)),"091","E")
