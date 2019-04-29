TicketSupervisor, a personal assistant to proecss simple ServiceNow tickets
===========================================================================

Hi :) I'm codename "**Paavo**" (just a randomly picked first name of a Finnish male), a simple robot that can help your team manage ServiceNow tickets.

I can be started to run on your desktop (at least Windows 10, linux) to run cyclic loops to find e.g. mathinc incident tickets and perform small updates (like assign, resolve) to them.

In order for me to become functional, you're kindly adviced
* to have python (preferably version 3) and some additional libraries installed. Alternatively on Windows, you can run the attached exe.
* to update the small configuration file that contains details of the target ServiceNow instance and related credentials.
* to check/update the rules that are processed to find and act on selected tickets that the defined user can see.
* to start up and give it a try


Installation instructions
-------------------------

You do not need to do these if you run the Windows exe (found on dist directory), but it starts a bit slow (takes 10ish seconds to unpack all on a standard laptop). This can be used e.g. on workstations with no admin authority or reach to relevant download sites.
~~~
install python (preferable (tested on) v3)
pip install pyyaml
pip install pysnow
~~~

Sample of my configuration file, TicketSupervisor.cfg
-----------------------------------------------------
~~~
- global:
    hello: world
    log_dir: "."                       # Log to current directory
    appname: Paavo                     # Name of the robot
    snc: sss                           # 1st qualifier of ServiceNow URL
    user: uuu                          # A valid user id for the ServiceNow
    pwd: "ppp"                         # Password here, or as start argument -p
    ignore_case: True                  # Do not care about the casing when matching
    first_match_only: True             # Process just the first matchinf rule
#   proxy: http://rrr:8080             # Proxy, in case needed
#   sleep_sec_between: 20              # Wait time in seconds between loops
#   snc_table: incident                # Name of snc table to process, e.g. sc_req_item
#   snc_state_ignore: 6                # States to deliberately avoid, e.g. ["8","9"]
#   snc_assign_group: "xxx"            # Force finding on this group only (specify sysid)
~~~


Sample of my ticket rule file, Paavo.txt
----------------------------------------
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


Sample startup arguments
------------------------
~~~
TicketSupervisor --simulate --once                  # Find but do not act, run just once
TicketSupervisor --show1 INCnnnnn                   # Show all attributes of a ticket, to e.g. see the field names

TicketSupervisor                                    # Run as continuous process, daemon
~~~


A longer syntax diagram of the configuration, Paavo.txt
-------------------------------------------------------
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
  - [snc_field]: "@now - 2m30s"               # matches if the datetime on the field is between now and now - 2min 30sec
  - [snc_field]: "^@now - 7h45m"              # matches if the datetime on the field is older than 7hrs 45min ago
  act:
  - nop                                       # show on log only
  - update:
    [snc_field1]: "[new_value1]"                              # update a new fixed value to the field
    [snc_field2]: "[new_value2] {snc_field} {env_variable}"   # update a new value with variale substitution
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

More on variables
-----------------

As said, you can use variable substitution. The bu default available variables are all fields on the ServiceNow ticket and all environment variables visibke on your command shell (use set on windows / env on linux to see them).

In addition, you can define files with name [appname]-vars-*.txt (e.g. Paavo-vars-test.txt) that are read in for additional variables
~~~
# Paavo-vars-test.txt
VAR_NAME: "Value"
ANOTHER: "Hello, world!"
~~~

Examples of variables:
* **number** The ticket number of current ServiceNow Ticket
* **USERNAME** The current user running the TicketSupervisor (on Windows, **LOGNAME** is the same in linux)
* **VAR_NAME** The value is to be assigned based on the contents of the previous variable file

Still more on everything else
-----------------------------

When requested so, I keep running forever, having a delay (of default 20 seconds) between each run. On each run, I read in the ticket rule file and the variable files.

Commonly found symptoms and resolutions
* **HTTP code 401** means the ServiceNow userid and password are invalid for the instance. They are specified either on TicketSupervisor.cfg or as command line argument
* **If I cannot read the configuration**, it normally is a sign of use of TAB characters. The yaml file format requires blanks, no TABs.
* **If I cannot change some (pull-down) values** on the ticket or do it incorrectly, it can be a cause of languages. Please use the same language settings (preferaly English) both on the rules on Paavo.txt and the user preferences on ServiceNow.
* **If I keep doing the same thing over and over again**, I am sorry. I'm just a siple robot that does exactly what is requested. To bypass, you could use more precise match argument (e.g. updated_at: "@now - 30s")


License: MIT
------------

Copyright 2019 Teemu Anttila

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


