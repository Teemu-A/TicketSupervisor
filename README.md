# TicketSupervisor
"a personal assistant to process simple ServiceNow tickets"

Hi :) I'm code name "**Paavo**" (just a randomly picked first name of a Finnish male), a simple robot that can help your team manage ServiceNow tickets.

I can be started to run on your desktop (at least Windows 10, linux) to run cyclic loops to find e.g. matching ServiceNow (snc) incident tickets and perform small updates (like assign, resolve, log, run an external script/program).

## Getting Started

In order for me to become functional, you're kindly adviced
* to have python (preferably version 3) and some additional libraries installed. Alternatively on Windows, you can run the attached exe.
* to update the small configuration file that contains details of the target ServiceNow instance and related credentials.
* to check/update the rules that are processed to find and act on selected tickets that the defined user can see.
* to start up and give it a try


### Prerequisites

You do not need to do these if you run the Windows exe (found on dist directory), but it starts a bit slow (takes 10ish seconds to unpack all on a standard laptop). This can be used e.g. on workstations with no admin authority or reach to relevant download sites.
~~~
install python (preferable (tested on) v3)
pip install pyyaml
pip install pysnow
~~~

### TicketSupervisor.cfg, the environment configuration file

The minimum to specify is ServiceNow instance, user and password

~~~
- global:
    hello: world
    log_dir: "."                       # Log to current directory
    appname: Paavo                     # Name of the robot
    snc: sss                           # 1st qualifier of ServiceNow URL
    user: uuu                          # A valid user id for the ServiceNow
    pwd: "ppp"                         # Password here, or as start argument -p
    ignore_case: True                  # Do not care about the casing when matching
    first_match_only: True             # Process just the first matching rule
#   proxy: http://rrr:8080             # Proxy, in case needed
#   sleep_sec_between: 20              # Wait time in seconds between loops
#   snc_table: incident                # Name of snc table to process, e.g. sc_req_item
#   snc_state_ignore: 6                # States to deliberately avoid, e.g. ["8","9"]
#   snc_assign_group: "xxx"            # Force finding on this group only (specify sysid)
#   snc_comment_field: "work_notes"    # Own comments goes to this field
#   ext_cmd_timeout: 30                # Stop external script/program after 30 seconds
~~~


### Paavo.txt, ticket rules

This file contains my rules to process tickets. I read it each time I start a new loop (default: 20 sec).

The file needs to be on yaml format, with blanks and no TAB characters.

~~~
###############################################################################################################
# A test set of paramerers to find and change arrived incident tickets
###############################################################################################################
- name: TestRule1_resolve
  find:
  - short_description: "Test ticket"
  - description: "Automatic"
  - description: "close"
  - state: "1"                                      # New
  act:
  - update:
      close_code: "Information"
      close_notes: "Thank you for the information. This ticket is automatically closed."
      state: 6                                      # Resolved
###############################################################################################################
- name: TestRule2_assign
  find:
  - short_description: "Test ticket"
  - description: "Automatic assign"
  - state: "1"                                      # New
  - assigned_to: "="                                # Exactly empty, no value
  act:
  - update:
      state: "Assigned"
      assignment_group: "[group name]"              # Fill in a relevant group, or just remove the line
      assigned_to: "[SNC incident agent]"           # Fill in a relevant user id / name
###############################################################################################################
- name: TestRule3_do_nothing
  find:
  - short_description: "Test ticket"
  - description: "^Production"                      # Must not contain to match
  - description: "~please|kind"                     # Regexp: Searched for either string
  - state: ["1","2"]                                # New or assigned
  - assigned_to: "="                                # Exactly empty, no value
  - priority: "4"                                   # Low
  - created_at: "^@now - 8m"                        # Created more than 8h ago
  act:
  - nop
###############################################################################################################
~~~


### Start up and test

Testing works with --simulate argument: I read the tickets but log only the actions I would perform if I had permission to do so.

~~~
TicketSupervisor --simulate --once                  # Find but do not act, run just once
TicketSupervisor --show1 INCnnnnn                   # Show all attributes of a ticket, to e.g. see the field names

TicketSupervisor --quiet                            # Run as continuous process (daemon) and log only actions
~~~

## Getting Deeper

TL;DR: Basically, you do not need to get further unless you really want to.

### A longer syntax diagram of the configuration, Paavo.txt

~~~
# Comment
- name: "[unique_name_of_a_rule]"
  find:
  - [snc_field]: "[value]"                    # matches if field contains value on any place
  - [snc_field]: "^[value]"                   # matches if field does not contain value
  - [snc_field]: "~[regex]"                   # matches if field matches the regexp
  - [snc_field]: "^~[regex]"                  # matches if field does not match the regexp
  - [snc_field]: "*[another_snc_field]"       # matches if the other snc field is part of this field
  - [snc_field]: "^*[another_snc_field]"      # matches if the other snc field is not part of this field  
  - [snc_field]: "^~{VAR_NAME}"               # matches if field does not match the regexp identified on stopword variable VAR_NAME
  - [snc_field]: "@now - 2m30s"               # matches if the datetime on the field is between now and now - 2min 30sec
  - [snc_field]: "^@now - 7h45m"              # matches if the datetime on the field is older than 7hrs 45min ago
  act:
  - nop                                       # show on log only
  - update:
    [snc_field1]: "[new_value1]"                              # update a new fixed value to the field
    [snc_field2]: "[new_value2] {snc_field} {env_variable}"   # update a new value with variale substitution
    [snc_field3]: ["[value1]","[value2]","[value3]"]          # pick randomly one from the list and use it for updating
    assigned_to: "{VAR_NAME}"                                 # Assign to someone described on variable VAR_NAME
  - run1:                                                     # Start an external process with arguments
    cmd: "[script_or_pgm] fix_arg {number} {USERNAME} {tkt_json_file}"   # SNC ticket #, env.var of username, name of file with all details from ticket (json)
# New comment
- name: "[another_rule]
  find:
  ...
  act:
  ...
...
~~~

### More on variables

As said, you can use variable substitution. The by default available variables are all fields on the ServiceNow ticket and all environment variables visible on your command shell (use set on windows / env on linux to see them).

In addition, you can define files with name `[appname]-vars-*.txt` (e.g. Paavo-vars-test.txt) that I read in for additional variables.
~~~
# Paavo-vars-test.txt
VAR_NAME: "Value"
ANOTHER: "Hello, world!"
~~~

Examples of variables:
* `number` The ticket number of current ServiceNow Ticket
* `USERNAME` The current user running the TicketSupervisor (on Windows, **LOGNAME** is the same in linux)
* `VAR_NAME` The value is to be assigned based on the contents of the previous variable file

### Commonly found symptoms and resolutions
* **HTTP code 401** means the ServiceNow userid and password are invalid for the instance. They are specified either on TicketSupervisor.cfg or as command line argument
* **If I cannot read the configuration**, it normally is a sign of use of TAB characters. The yaml file format requires blanks, no TABs.
* **If I cannot change some (pull-down) values** on the ticket or do it incorrectly, it can be a cause of languages. Please use the same language settings (preferably English) both on the rules on Paavo.txt and the user preferences on ServiceNow.
* **If I keep doing the same thing over and over again**, I am sorry. I'm just a siple robot that does exactly what is requested. To bypass, you could use more precise match argument (e.g. updated_at: "@now - 30s")

### Logging
I log both on console output and logfile, which format is `actions-Paavo-YYYYMMDD.log`.
The 1st word of the log message is a message id (thanks, IBM mainframes, learned at least that from there). The 2nd word of the message is a timestamp of format DD-HHMMSS, and the rest of it contains meaningful information related to the message.
If you specify `--debug` as run argument, I'll be loud and you'll get a whole lot of messages. If you specify `--quiet`, I'll inform only when I do actions on matching tickets.
I do have a small utility to summarize from the log files as well. It is the ReportTicketSupervisor. Just run it once you have some logs to see how it works.
~~~
PVE008I YY-HHMMSS Initialized by [USER] at [WS], [version], [appname] service awake, cfg @ [rulefile], starting to talk to SNC [instance]. To stop, Ctrl-C or close the window.
PVE009I YY-HHMMSS ... right now, nnn eligible tickets.
PVE202I YY-HHMMSS #INCnnnnnn1 == [matched_rule_name] - [short_description]
PVE402I YY-HHMMSS #INC0053125 -> update: '{'state': 'Assigned', 'assigned_to': '[name]', 'comments': 'PVE402I Paavo -> [matched_rule_name]'}' -> <Response [200 - PUT]>
PVE201I YY-HHMMSS #INCnnnnnn2 NA - [short_description_of_non_matching_ticket]
PVE201I YY-HHMMSS #INCnnnnnn3 NA - [short_description_of_non_matching_ticket]
~~~

### Messages
The 1st word contains a fixed string "PVE", a number and a character. The number shows the place in code / function that caused the message, and the character the severity of the message (D=debug,I=info, W=warning, E=error - kudos to [IBM](https://www.google.com/search?q=ibm+message+severity+tags) for that).
~~~
PVE000I When run with --version, printout of version number and immediate exit
PVE008I Startup message with all the nice details of who/why/what/where/when ... or so
PVE009I Number of initially qualifying tickets found
PVE091E I really wasn't feeling well and went on a sick leave. Did you feed me something bad?
PVE191E Something bad happened on processing tickets. Will continue on the next round.
PVE192E So sorry, but I ended up into an error on this ticket. Will continue with the next ticket.
PVE201I This ticket did not match any rule, and I ignored it (with `--quiet` ,will not show this)
PVE202I Yippee, I found a ticket that matches a rule and will do some actions to it :)
PVE391W I encountered an error processing a match rule, and skipped the processing of the ticket
PVE401I Showing happiness of executing nop (no operation) to the ticket
PVE402I Result of a ticket update, containing details updated and the (HTTP) response code - 200 = done successfully
PVE403I Printing the external script/command and its response code
PVE404I Printout of the stderr (standard error) of the script/command that I ran
PVE405I Printout of the stdout (standard output) of the script/command that I ran
PVE491E While processing actions to a ticket, I regret of encountering an error which is described here. Actions to this ticket was terminated.

Debugging messages (that I will show only if you ask politely with --debug)
PVE181D I'm about to read a vars file, and would like to share it with you
PVE182D In addition to the fields on the ticket, the following variables are available for substitution
PVE800D Confirming the need of a proxy server that was given to me on the cfg file
PVE081D I'm just about to query data from SNC with these parameters
PVE382D Here's the result and criteria for a single match test for a ticket. If false, I will scan the next ticket
PVE481D After a found matching ticket, I'd like to share the details of an individual action to be performed
PVE281D I am about to process this rule against this ticket now. First check if it matches, then execute actions if matched
PVE001D During startup, I read the configuration file and echo back the contents of it
~~~

### Still more on everything else

When requested so, I keep running forever, having a delay (of default 20 seconds) between each run. On each run, I read in the ticket rule file and the variable files.
If you want to stop the execution, enter Ctrl-C, close the window, or restart the machine. One option is to run with `--once` which does not loop forever.

## License: MIT

Copyright 2019 Teemu Anttila

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Acknowledgments

Warm thanks:
* Robert Wikman for [pysnow](https://github.com/rbw/pysnow)
* Tina Müller for [PyYAML](https://github.com/yaml/pyyaml.org)
* Kenneth Reit for [requests](https://pypi.org/project/requests/)
