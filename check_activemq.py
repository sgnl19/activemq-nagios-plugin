#!/usr/bin/env python
# -*- coding: utf-8 *-*

"""	Copyright 2015 predic8 GmbH, www.predic8.com

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License. """

""" Project Home: https://github.com/predic8/activemq-nagios-plugin """

import os
import os.path as path
import urllib
import json
import argparse
import fnmatch
import nagiosplugin as np
import logging, sys
from math import isinf

PLUGIN_VERSION = "0.0.1"

PREFIX = 'org.apache.activemq.artemis:'
BROKER_OBJECT_NAME = PREFIX + 'broker="%s"'
QUEUE_OBJECT_NAME = BROKER_OBJECT_NAME + ',component=addresses,address="%s",subcomponent=queues,routing-type="anycast",queue="%s"'

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)


def make_url(args, dest):

    url = (
        (args.jolokia_url + ('' if args.jolokia_url[-1] == '/' else '/') + dest)
        if args.jolokia_url
        else ('http://' + args.user + ':' + args.pwd
              + '@' + args.host + ':' + str(args.port)
              + '/' + args.url_tail + '/' + dest)
    )
    if args.debug:
        logging.debug('url: %s', url)
    return url

def queue_url(args, queue):
    if not args.address:
        args.address = queue
    return make_url(args, (QUEUE_OBJECT_NAME % (args.broker, args.address, queue)).replace('"', '%22'))

def broker_url(args, property):
    return make_url(args, (BROKER_OBJECT_NAME % args.broker).replace('"', '%22')) + '/' + property

def health_url(args):
    return broker_url(args, 'Started')

def message_url(args, queue, kind = "Count"):
    msg = 'Message'
    if kind.capitalize() != "Count":
        msg = 'Messages'
    return queue_url(args, queue) + '/' + msg + kind.capitalize()


def loadJson(srcurl):
    jsn = urllib.urlopen(srcurl)
    return json.loads(jsn.read())


def query_object(args):
    class ActiveMqCheckObjectContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            critical = get_threshold(self.critical)
            warning = get_threshold(self.warning)
            if metric.value['status'] < 0 or ((self.critical.end or self.warning.end) and metric.value['value'] < 0):
                return self.result_cls(np.unknown, None, metric)

            if metric.value['status'] >= 400:
                return self.result_cls(np.Critical, None, metric)

            if metric.value['status'] > 200:
                return self.result_cls(np.Warn, None, metric)

            if metric.value['value'] >= critical:
                return self.result_cls(np.Critical, ActiveMqCheckObjectContext.fmt_violation(critical), metric)

            if metric.value['value'] >= warning:
                return self.result_cls(np.Warn, ActiveMqCheckObjectContext.fmt_violation(warning), metric)

            return self.result_cls(np.Ok, None, metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return super(ActiveMqCheckObjectContext, self).describe(metric)

        @staticmethod
        def fmt_violation(max_value):
            return 'Given broker property %s' % max_value

    class ActiveMqCheckObject(np.Resource):
        def probe(self):
            try:
                result = loadJson(make_url(args, args.activeMqOject.replace('&quot;', '%22')))
                return np.Metric('result', result, context='check_object')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='check_object')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='check_object')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='check_object')

    np.Check(
        ActiveMqCheckObject(),
        ActiveMqCheckObjectContext('check_object', args.warn, args.crit)
    ).main(timeout=get_timeout())

def broker_property(args):
    class ActiveMqCheckBrokerContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            critical = get_threshold(self.critical)
            warning = get_threshold(self.warning)
            if metric.value['status'] < 0 or ((self.critical.end or self.warning.end) and metric.value['value'] < 0):
                return self.result_cls(np.Unknown, None, metric)

            if metric.value['status'] >= 400:
                return self.result_cls(np.Critical, None, metric)

            if metric.value['status'] > 200:
                return self.result_cls(np.Warn, None, metric)

            if metric.value['value'] >= critical:
                return self.result_cls(np.Critical, ActiveMqCheckBrokerContext.fmt_violation(critical), metric)

            if metric.value['value'] >= warning:
                return self.result_cls(np.Warn, ActiveMqCheckBrokerContext.fmt_violation(warning), metric)

            return self.result_cls(np.Ok, None, metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return super(ActiveMqCheckBrokerContext, self).describe(metric)

        @staticmethod
        def fmt_violation(max_value):
            return 'Given broker property %s' % max_value

    class ActiveMqCheckBroker(np.Resource):
        def probe(self):
            try:
                result = loadJson(broker_url(args, args.property))
                return np.Metric('result', result, context='check_broker')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='check_broker')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='check_broker')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='check_broker')

    np.Check(
        ActiveMqCheckBroker(),
        ActiveMqCheckBrokerContext('check_broker', args.warn, args.crit)
    ).main(timeout=get_timeout())

def queuesize(args):
    class ActiveMqQueueSizeContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            critical = get_threshold(self.critical)
            warning = get_threshold(self.warning)
            if metric.value < 0:
                return self.result_cls(np.Unknown, metric=metric)

            if metric.value >= critical:
                return self.result_cls(np.Critical, ActiveMqQueueSizeContext.fmt_violation(critical), metric)

            if metric.value >= warning:
                return self.result_cls(np.Warn, ActiveMqQueueSizeContext.fmt_violation(warning), metric)

            return self.result_cls(np.Ok, None, metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return super(ActiveMqQueueSizeContext, self).describe(metric)

        @staticmethod
        def fmt_violation(max_value):
            return 'Queue size is greater than or equal to %s' % max_value

    class ActiveMqQueueSize(np.Resource):
        def __init__(self, pattern=None):
            self.pattern = pattern

        def probe(self):
            try:
                qresult = loadJson(broker_url(args, "AddressNames"))
                if qresult['status'] != 200:
                    raise KeyError(qresult['error']+" ("+qresult['error_type']+")")

                for queue in qresult['value']:
                    if args.address:
                        args.address = ""
                    if fnmatch.fnmatch(queue, 'activemq*'):
                        continue
                    if (self.pattern
                            and fnmatch.fnmatch(queue, self.pattern)
                            or not self.pattern):
                        queueSize = loadJson(message_url(args, queue, 'Count'))['value']
                        yield np.Metric('Queue Size of %s' % queue, queueSize, min=0, context='size')

            except IOError as e:
                yield np.Metric('Fetching network FAILED: ' + str(e), -1, context='size')
            except ValueError as e:
                yield np.Metric('Decoding Json FAILED: ' + str(e), -1, context='size')
            except KeyError as e:
                yield np.Metric('Getting Queue(s) FAILED: ' + str(e), -1, context='size')

    class ActiveMqQueueSizeSummary(np.Summary):
        def ok(self, results):

            if len(results) > 1:
                lenQ = str(len(results))
                minQ = str(min([r.metric.value for r in results]))
                avgQ = str(sum([r.metric.value for r in results]) / len(results))
                maxQ = str(max([r.metric.value for r in results]))
                return ('Checked ' + lenQ + ' queues with lengths min/avg/max = '
                        + '/'.join([minQ, avgQ, maxQ]))
            else:
                return super(ActiveMqQueueSizeSummary, self).ok(results)

    np.Check(
        ActiveMqQueueSize(args.queue) if args.queue else ActiveMqQueueSize(),
        ActiveMqQueueSizeContext('size', args.warn, args.crit),
        ActiveMqQueueSizeSummary()
    ).main(timeout=get_timeout())


# when debugging the application, set the TIMEOUT env variable to 0 to disable the timeout during check execution
def get_timeout():
    return int(os.environ.get('TIMEOUT')) if 'TIMEOUT' in os.environ else 10


def get_threshold(value):
    return value.start if isinf(value.end) else value.end


def health(args):
    class ActiveMqHealthContext(np.Context):
        def evaluate(self, metric, resource):
            if metric.value < 0:
                return self.result_cls(np.Unknown, metric=metric)
            if metric.value == True:
                return self.result_cls(np.Ok, metric=metric)
            else:
                return self.result_cls(np.Critical, metric=metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return metric.name + ' ' + str(metric.value)

    class ActiveMqHealth(np.Resource):
        def probe(self):
            try:
                status = loadJson(health_url(args))['value']
                return np.Metric('status', status, context='health')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='health')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='health')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='health')

    np.Check(
        ActiveMqHealth(),  ## check ONE queue
        ActiveMqHealthContext('health')
    ).main(timeout=get_timeout())

def message(args):
    class ActiveMqMessageContext(np.Context):
        def evaluate(self, metric, resource):
            if metric.value < 0:
                return self.result_cls(np.Unknown, metric=metric)
            if metric.value == True:
                return self.result_cls(np.Ok, metric=metric)
            else:
                return self.result_cls(np.Warn, metric=metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return metric.name + ' ' + str(metric.value)

    class ActiveMqMessage(np.Resource):
        def probe(self):
            try:
                status = loadJson(message_url(args, args.kind))['value']
                return np.Metric('status', status, context='message')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='message')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='message')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='message')

    np.Check(
        ActiveMqMessage(),  ## check ONE queue
        ActiveMqMessageContext('message')
    ).main(timeout=get_timeout())


def exists(args):
    class ActiveMqExistsContext(np.Context):
        def evaluate(self, metric, resource):
            if metric.value < 0:
                return self.result_cls(np.Unknown, metric=metric)
            if metric.value > 0:
                return self.result_cls(np.Ok, metric=metric)
            return self.result_cls(np.Critical, metric=metric)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            if metric.value == 0:
                return 'No Queue with name ' + args.queue + ' wasfound!'
            if metric.value == 1:
                return 'Found Queue with name ' + args.queue
            return super(ActiveMqExistsContext, self).describe(metric)

    class ActiveMqExists(np.Resource):
        def probe(self):
            try:
                respQ = loadJson(queue_url(args, args.queue))
                if respQ['status'] == 200:
                    return np.Metric('exists', 1, context='exists')

                return np.Metric('exists', 0, context='exists')

            except IOError as e:
                return np.Metric('Network fetching FAILED: ' + str(e), -1, context='exists')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='exists')
            except KeyError as e:
                return np.Metric('Getting Queue(s) FAILED: ' + str(e), -1, context='exists')

    np.Check(
        ActiveMqExists(),
        ActiveMqExistsContext('exists')
    ).main(timeout=get_timeout())


def dlq(args):
    class ActiveMqDlqScalarContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            if metric.value > 0:
                return self.result_cls(np.Critical, metric=metric)
            else:
                return self.result_cls(np.Ok, metric=metric)

    class ActiveMqDlq(np.Resource):
        def __init__(self, prefix, cachedir):
            super(ActiveMqDlq, self).__init__()
            self.cache = None
            self.cachedir = path.join(path.expanduser(cachedir), 'activemq-nagios-plugin')
            self.cachefile = path.join(self.cachedir, 'dlq-cache.json')
            self.parse_cache()
            self.prefix = prefix

        def parse_cache(self):  # deserialize
            if not os.path.exists(self.cachefile):
                self.cache = {}
            else:
                with open(self.cachefile, 'r') as cachefile:
                    self.cache = json.load(cachefile)

        def write_cache(self):  # serialize
            if not os.path.exists(self.cachedir):
                os.makedirs(self.cachedir)
            with open(self.cachefile, 'w') as cachefile:
                json.dump(self.cache, cachefile)

        def probe(self):
            try:
                for queue in loadJson(queue_url(args, 'DLQ'))['value']['Queues']:
                    qJ = loadJson(make_url(args, queue['objectName']))['value']
                    if qJ['Name'].startswith(self.prefix):
                        oldcount = self.cache.get(qJ['Name'])

                        if oldcount == None:
                            more = 0
                            msg = 'First check for DLQ'
                        else:
                            assert isinstance(oldcount, int)
                            more = qJ['QueueSize'] - oldcount
                            if more == 0:
                                msg = 'No additional messages in'
                            elif more > 0:
                                msg = 'More messages in'
                            else:  # more < 0
                                msg = 'Less messages in'
                        self.cache[qJ['Name']] = qJ['QueueSize']
                        self.write_cache()
                        yield np.Metric(msg + ' %s' % qJ['Name'],
                                        more, context='dlq')
            except IOError as e:
                yield np.Metric('Fetching network FAILED: ' + str(e), -1, context='dlq')
            except ValueError as e:
                yield np.Metric('Decoding Json FAILED: ' + str(e), -1, context='dlq')
            except KeyError as e:
                yield np.Metric('Getting Queue(s) FAILED: ' + str(e), -1, context='dlq')

    class ActiveMqDlqSummary(np.Summary):
        def ok(self, results):
            if len(results) > 1:
                lenQ = str(len(results))
                bigger = str(len([r.metric.value for r in results if r.metric.value > 0]))
                return ('Checked ' + lenQ + ' DLQs of which ' + bigger + ' contain additional messages.')
            else:
                return super(ActiveMqDlqSummary, self).ok(results)

    np.Check(
        ActiveMqDlq(args.prefix, args.cachedir),
        ActiveMqDlqScalarContext('dlq'),
        ActiveMqDlqSummary()
    ).main(timeout=get_timeout())


def add_warn_crit(parser, what):
    parser.add_argument('-w', '--warn',
                        metavar='WARN', type=int, default=5,
                        help='Warning if ' + what + ' is greater than or equal to. (default: %(default)s)')
    parser.add_argument('-c', '--crit',
                        metavar='CRIT', type=int, default=10,
                        help='Warning if ' + what + ' is greater than or equal to. (default: %(default)s)')


@np.guarded
def main():
    # Top-level Argument Parser & Subparsers Initialization
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--version', action='version',
                        help='Print version number',
                        version='%(prog)s version ' + str(PLUGIN_VERSION))

    parser.add_argument('-v', '--debug', type=bool, default=False,
                        help='Switch debug on')


    connection = parser.add_argument_group('Connection')

    connection.add_argument('--host', default='localhost',
                            help='ActiveMQ Artemis Server Hostname (default: %(default)s)')
    connection.add_argument('--port', type=int, default=8161,
                            help='ActiveMQ Artemis Server Port (default: %(default)s)')
    connection.add_argument('-b', '--broker', default='0.0.0.0',
                            help='Name of your broker. (default: %(default)s)')
    connection.add_argument('--url-tail',
                            default='console/jolokia/read',
                            # default='hawtio/jolokia/read',
                            help='Jolokia URL tail part. (default: %(default)s)')
    connection.add_argument('-j', '--jolokia-url',
                                help='''Override complete Jolokia URL.
                                (Default: "http://USER:PWD@HOST:PORT/URLTAIL/").
                                The parameters --user, --pwd, --host and --port are IGNORED
                                if this paramter is specified!
                                Please set this parameter carefully as it essential
                                for the program to work properly and is not validated.''')

    credentials = parser.add_argument_group('Credentials')
    credentials.add_argument('-u', '--user', default='admin',
                             help='Username for ActiveMQ admin account. (default: %(default)s)')
    credentials.add_argument('-p', '--pwd', default='admin',
                             help='Password for ActiveMQ admin account. (default: %(default)s)')

    subparsers = parser.add_subparsers()

    # Sub-Parser for objects
    parser_query_object = subparsers.add_parser('activeMqOject',
                                                help="""Check QueueSize: This mode checks the queue size of one
                                                or more queues on the ActiveMQ server.
                                                You can specify a queue name to check (even a pattern);
                                                see description of the 'queue' paramter for details.""")
    add_warn_crit(parser_query_object, 'Object Threshold')
    parser_query_object.add_argument('activeMqOject', nargs='?',
                                    help='''Name of the Object that will be checked.
                                    If left empty, all Objects will be checked.
                                    This also can be a Unix shell-style Wildcard
                                    (much less powerful than a RegEx)
                                    where * and ? can be used.''')
    parser_query_object.set_defaults(func=query_object)

    # Sub-Parser for queuesize
    parser_queuesize = subparsers.add_parser('queuesize',
                                                help="""Check QueueSize: This mode checks the queue size of one
                                                or more queues on the ActiveMQ server.
                                                You can specify a queue name to check (even a pattern);
                                                see description of the 'queue' paramter for details.""")

    add_warn_crit(parser_queuesize, 'Property Threshold')
    parser_queuesize.add_argument('--address', required=False,
                               help='Name of the Address of the Queue that will be checked.')
    parser_queuesize.add_argument('queue', nargs='?',
                                    help='''Name of the Queue that will be checked.
                                    If left empty, all Queues will be checked.
                                    This also can be a Unix shell-style Wildcard
                                    (much less powerful than a RegEx)
                                    where * and ? can be used.''')
    parser_queuesize.set_defaults(func=queuesize)

    # Sub-Parser for health
    parser_health = subparsers.add_parser('health',
                                          help="""Check Health: This mode checks if the broker's started status is 'True'.""")
    # no additional arguments necessary
    parser_health.set_defaults(func=health)

    # Sub-Parser for broker property
    parser_broker_property = subparsers.add_parser('broker_property',
                                                    help="""Request API with given broker property: This mode quries 
                                                    the API with the given broker property.""")
    add_warn_crit(parser_broker_property, 'Property Threshold')
    parser_broker_property.add_argument('--property', required=True,
                                        help='Broker Property to request the API with')
    # no additional arguments necessary
    parser_broker_property.set_defaults(func=broker_property)

    # Sub-Parser for message
    parser_message = subparsers.add_parser('message',
                                          help="""Check Message*: This mode checks if the current status is 'Good'.""")
    parser_message.add_argument('--address', required=False,
                               help='Name of the Address of the Queue that will be checked.')
    parser_message.add_argument('--kind', required=True,
                                   help='Kind of message to check')
    # no additional arguments necessary
    parser_message.set_defaults(func=message)

    # Sub-Parser for exists
    parser_exists = subparsers.add_parser('exists',
                                            help="""Check Exists: This mode checks if a Queue with the given name exists.
                                            If a Queue with this name exist, this mode yields OK.""")
    parser_exists.add_argument('--address', required=False,
                               help='Name of the Address of the Queue that will be checked.')
    parser_exists.add_argument('--queue', required=True,
                               help='Name of the Queue that will be checked.')
    parser_exists.set_defaults(func=exists)

    # Sub-Parser for dlq
    parser_dlq = subparsers.add_parser('dlq',
                                        help="""Check DLQ (Dead Letter Queue):
                                        This mode checks if there are new messages in DLQs
                                        with the specified prefix.""")
    parser_dlq.add_argument('--address', required=False,
                               help='Name of the Address of the Queue that will be checked.')
    parser_dlq.add_argument('--prefix',  # required=False,
                            default='ActiveMQ.DLQ.',
                            help='DLQ prefix to check. (default: %(default)s)')
    parser_dlq.add_argument('--cachedir',  # required=False,
                            default='~/.cache',
                            help='DLQ cache base directory. (default: %(default)s)')
    add_warn_crit(parser_dlq, 'DLQ Queue Size')
    parser_dlq.set_defaults(func=dlq)

    # Evaluate Arguments
    args = parser.parse_args()
    # call the determined function with the parsed arguments
    args.func(args)


if __name__ == '__main__':
    main()
