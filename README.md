# ActiveMQ Artemis Nagios Plugin
Monitor Apache ActiveMQ's health, queuesizes and subscribers. The plugin makes use of the Jolokia REST interface.


## Requirements (tested with):
- ActiveMQ Artemis starting from version 2.5.0
- Python 2.7
- nagiosplugin 1.2.2

nagiosplugin is a Python Framework designed for Nagios Plugins written in Python.
It can be installed via ```pip```.


## Supported ActiveMQ Artemis Versions
The plugin queries ActiveMQ Artemis using the new REST based [Jolokia](https://jolokia.org/) interface.

### ActiveMQ Artemis < 5.9.1
If you run a version of ActiveMQ Artemis that still includes Hawtio,
you need to supply the ```--url-tail "hawtio/jolokia/read"``` parameter to the plugin.

For releases without Hawtio, this paramter can be omitted and defaults to ```console/jolokia/read```.


## Installation

1. Navigate to the folder where your nagios plugins are stored e.g.:
 - ```cd /usr/lib/nagios/plugins/```
- Download the plugin script:
 - ```wget https://raw.githubusercontent.com/sgnl19/activemq-nagios-plugin/master/check_activemq.py```
- Install nagiosplugin for Python:
 - ```pip install nagiosplugin``` (systemwide, execute as root) or
 - ```pip install --user nagiosplugin``` (for the current user)


## Command line options:
- Run ```./check_activemq.py -h``` to see the full (and up to date) help
- ```--host``` specifies the Hostname of the ActiveMQ Artemis broker
- ```--port``` specifies the Port
- ```--user``` specifies the Username of ActiveMQ Artemis's Web Console
- ```--pwd``` specifies the Password


## Checks

This Plugin currently support 6 different checks listed below.
All checks return UNKNOWN if the broker isn't reachable on the network.

### broker_health
- Checks if the broker is started.
- Returns OK or WARN.

### queuesize
- Check the size of one or more Queues.
- Additional parameters:
 - ```-w WARN``` specifies the Warning threshold (default 10)
 - ```-c CRIT``` specifies the Critical threshold (default 100)
 - ```QUEUE``` - specify queue name to check (see additional explanations below)
- If queuesize is called WITH a queue then this explicit queue name is checked.
 - A given queue name can also contain shell-like wildcards like ```*``` and ```?```

### exists
- Checks if a Queue Topic with the specified `queue` exists.
- Mandatory parameters:
 - ```--queue``` specifies a Queue name
- Optional parameters:
 - ```--address``` specifies a Queue address. If omitted query will be assumed as address.
 - ```--type``` specifies a Queue type (anycast or multicast - defaults to anycast)
- Returns Critical if no Queue with the given `queue` exist.

### broker_property
- Checks any property provided by the broker.
- Mandatory parameters:
 - ```--property PROPERTY``` the property to check
- Additional parameters:
 - ```--check CHECK``` `true|false` whether or not to validate the result against the threshold values
 - ```-w WARN``` specifies the Warning threshold (default 5)
 - ```-c CRIT``` specifies the Critical threshold (default 10)
- Returns Critical
 - if the API returns an HTTP status >= 400
 - if ```-c CRIT``` is given and the result is >= `CRIT`
- Returns Warning
 - if ```-w WARN``` is given and the result is >= `WARN`

### query_object
- Checks any property provided by any object.
- Additional parameters:
 - ```--check CHECK``` `true|false` whether or not to validate the result against the threshold values
 - ```-w WARN``` specifies the Warning threshold (default 5)
 - ```-c CRIT``` specifies the Critical threshold (default 10)
- Returns Critical
 - if the API returns an HTTP status >= 400
 - if ```-c CRIT``` is given and the result is >= `CRIT`
- Returns Warning
 - if ```-w WARN``` is given and the result is >= `WARN`

### dlq_expiry_check
- Check if there are new messages in a DLQ (Dead Letter Queue) or the ExpiryQueue.
- Additional parameters:
 - ```--prefix PREFIX``` - specify DLQ prefix, all queues with a matching prefix will be checked (default 'ActiveMQ Artemis.DLQ.')
 - ```--cache_dir CACHEDIR``` - specify base directory for state file (default '~/.cache')
- Returns Unknown if no DLQ/Expiry Queue was found.
- Returns Critical if one of the Queues contains more messages since the last check.
- This mode saves it's state in the file
  ``CACHEDIR/activemq-nagios-plugin/dlq-cache.json``
- When you want to use this check, it is recommended that you invoke the
  plugin rather often from Nagios (e.g. every minute or every 30 seconds)
  to have a better coverage of your ActiveMQ Artemis' state.
- Note (this might lead to confusion): When the plugin yields a message for
  a specific queue (e.g. ``'No additional messages in ActiveMQ Artemis DLQ'=0``)
  the `=0` means that there are `0` additional messages since the last check,
  it does NOT mean that there are `0` messages in the queue. (Use `queuesize`
  if you want to check this.)


## Examples: Check
- the queue size of the queue TEST
 - ```./check_activemq.py queuesize TEST```
- the queue sizes of all queues starting with TEST
 - ```./check_activemq.py -w 30 -c 100 queuesize "TEST*"```
- the overall health of the ActiveMQ Artemis Broker
 - ```./check_activemq.py health```
- if a queue with a given name exists
 - ```./check_activemq.py exists --queue someQueueName```
- the specific property of the broker
 - ```./check_activemq.py query_object broker_property --property AddressMemoryUsagePercentage -c 15 -w 10```
- the specific property of an object which should not be validates against threshold values
 - ```./check_activemq.py query_object org.apache.activemq.artemis:broker=&quot;0.0.0.0&quot;,component=addresses,address=&quot;SearchUpdateService.v1.Request&quot;,subcomponent=queues,routing-type=&quot;anycast&quot;,queue=&quot;SearchUpdateService.v1.Request&quot;/ExpiryAddress --check False```
- if there are new messages in the Dead Letter Queue
 - ```./check_activemq.py dlq_expiry_check --address DLQ```
