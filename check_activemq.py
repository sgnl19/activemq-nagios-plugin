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

import os
import os.path as path
import urllib
import json
import argparse
import fnmatch

import nagiosplugin as np
import logging
import sys
from math import isinf

""" Project Home: https://github.com/sgnl19/activemq-nagios-plugin """

PLUGIN_VERSION = "0.0.1"
PREFIX = 'org.apache.activemq.artemis:'
BROKER_OBJECT_NAME = PREFIX + 'broker="%s"'
QUEUE_OBJECT_NAME = BROKER_OBJECT_NAME + \
                    ',component=addresses,address="%s",subcomponent=queues,routing-type="%s",queue="%s"'

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
    return make_url(args, (QUEUE_OBJECT_NAME % (args.broker, args.address, args.type, queue)).replace('"', '%22'))


def broker_url(args, broker_prop):
    return make_url(args, (BROKER_OBJECT_NAME % args.broker).replace('"', '%22')) + '/' + broker_prop


def dlq_expiry_url(args):
    return make_url(
        args, (QUEUE_OBJECT_NAME % (args.broker, args.address, 'anycast', args.address)).replace('"', '%22'))


def message_url(args, queue, kind="Count"):
    msg = 'Message'
    current_kind = kind.capitalize()
    if current_kind != "Count":
        msg = 'Messages'
    return queue_url(args, queue) + '/' + msg + current_kind


def load_json(srcurl):
    jsn = urllib.urlopen(srcurl)
    return json.loads(jsn.read())


def check_http_status(clazz, metric):
    if metric.value['status'] < 0 or ((clazz.critical.end or clazz.warning.end) and metric.value['value'] < 0):
        return clazz.result_cls(np.Unknown, None, metric)

    if metric.value['status'] >= 400:
        return clazz.result_cls(np.Critical, None, metric)

    if metric.value['status'] > 200:
        return clazz.result_cls(np.Warn, None, metric)

    return np.Ok


def check_metric(clazz, metric, check=True):
    critical = get_threshold(clazz.critical)
    warning = get_threshold(clazz.warning)
    if check is True and metric.value < 0:
        return clazz.result_cls(np.Unknown, metric=metric)

    if check is True and metric.value >= critical:
        return clazz.result_cls(np.Critical, clazz.fmt_violation(critical), metric)

    if check is True and metric.value >= warning:
        return clazz.result_cls(np.Warn, clazz.fmt_violation(warning), metric)

    return clazz.result_cls(np.Ok, metric=metric)
    # return clazz.result_cls(np.Ok, None, metric)


def query_object(args):

    class ActiveMqCheckObjectContext(np.ScalarContext):

        def evaluate(self, metric, resource):
            http_check = check_http_status(self, metric)
            if http_check is not np.Ok:
                return http_check

            return check_metric(self, metric, args.check)

        def describe(self, metric):
            if metric.value < 0:
                return 'ERROR: ' + metric.name
            return super(ActiveMqCheckObjectContext, self).describe(metric)

        @staticmethod
        def fmt_violation(max_value):
            return 'Given object property %s' % max_value

    class ActiveMqCheckObject(np.Resource):
        def probe(self):
            try:
                result = load_json(make_url(args, args.object.replace('&quot;', '%22')))
                return np.Metric('result', result, context='query_object')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='query_object')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='query_object')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='query_object')

    class ActiveMqQueueCheckObjectSummary(np.Summary):
        def ok(self, results):

            return super(ActiveMqQueueCheckObjectSummary, self).ok(results)

    np.Check(
        ActiveMqCheckObject(),
        ActiveMqCheckObjectContext('query_object', args.warn, args.crit),
        ActiveMqQueueCheckObjectSummary()
    ).main(timeout=get_timeout())


def broker_property(args):
    class ActiveMqCheckBrokerContext(np.ScalarContext):

        def evaluate(self, metric, resource):
            http_check = check_http_status(self, metric)
            if http_check is not np.Ok:
                return http_check

            return check_metric(self, metric, args.check)

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
                result = load_json(broker_url(args, args.property))
                return np.Metric('result', result, context='broker_property')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='broker_property')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='broker_property')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='broker_property')

    class ActiveMqQueueCheckBrokerSummary(np.Summary):
        def ok(self, results):
            logging.debug('results: %s', results)
            return super(ActiveMqQueueCheckBrokerSummary, self).ok(results)

    np.Check(
        ActiveMqCheckBroker(),
        ActiveMqCheckBrokerContext('broker_property', args.warn, args.crit),
        ActiveMqQueueCheckBrokerSummary()
    ).main(timeout=get_timeout())


def queue_size(args):
    class ActiveMqQueueSizeContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            return check_metric(self, metric)

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
                qresult = load_json(broker_url(args, "AddressNames"))
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
                        queue_size = load_json(message_url(args, queue, 'Count'))['value']
                        yield np.Metric('Queue Size of %s' % queue, queue_size, min=0, context='queue_size')

            except IOError as e:
                yield np.Metric('Fetching network FAILED: ' + str(e), -1, context='queue_size')
            except ValueError as e:
                yield np.Metric('Decoding Json FAILED: ' + str(e), -1, context='queue_size')
            except KeyError as e:
                yield np.Metric('Getting Queue(s) FAILED: ' + str(e), -1, context='queue_size')

    class ActiveMqQueueSizeSummary(np.Summary):
        def ok(self, results):

            if len(results) > 1:
                len_q = str(len(results))
                min_q = str(min([r.metric.value for r in results]))
                avg_q = str(sum([r.metric.value for r in results]) / len(results))
                max_q = str(max([r.metric.value for r in results]))
                return ('Checked ' + len_q + ' queues with lengths min/avg/max = '
                        + '/'.join([min_q, avg_q, max_q]))
            else:
                return super(ActiveMqQueueSizeSummary, self).ok(results)

    np.Check(
        ActiveMqQueueSize(args.queue) if args.queue else ActiveMqQueueSize(),
        ActiveMqQueueSizeContext('queue_size', args.warn, args.crit),
        ActiveMqQueueSizeSummary()
    ).main(timeout=get_timeout())


# when debugging the application, set the TIMEOUT env variable to 0 to disable the timeout during check execution
def get_timeout():
    return int(os.environ.get('TIMEOUT')) if 'TIMEOUT' in os.environ else 10


def get_threshold(value):
    return value.start if isinf(value.end) else value.end


def broker_health(args):
    class ActiveMqHealthContext(np.Context):
        def evaluate(self, metric, resource):
            if metric.value < 0:
                return self.result_cls(np.Unknown, metric=metric)
            if metric.value is True:
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
                status = load_json(broker_url(args, 'Started'))['value']
                return np.Metric('status', status, context='health')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='health')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='health')
            except KeyError as e:
                return np.Metric('Getting Values FAILED: ' + str(e), -1, context='health')

    np.Check(
        ActiveMqHealth(),  # check ONE queue
        ActiveMqHealthContext('health')
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
                resp_q = load_json(queue_url(args, args.queue))
                if resp_q['status'] == 200:
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


def dlq_expiry(args):
    class ActiveMqDlqScalarContext(np.ScalarContext):
        def evaluate(self, metric, resource):
            if metric.value > 0:
                return self.result_cls(np.Critical, metric=metric)
            else:
                return self.result_cls(np.Ok, metric=metric)

    class ActiveMqDlq(np.Resource):
        def __init__(self, cache_dir):
            super(ActiveMqDlq, self).__init__()
            self.cache = None
            self.cache_dir = path.join(path.expanduser(cache_dir), 'activemq-nagios-plugin')
            self.cachefile = path.join(self.cache_dir, 'dlq-cache.json')
            self.parse_cache()

        def parse_cache(self):  # deserialize
            if not os.path.exists(self.cachefile):
                self.cache = {}
            else:
                with open(self.cachefile, 'r') as cachefile:
                    self.cache = json.load(cachefile)

        def write_cache(self):  # serialize
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir)
            with open(self.cachefile, 'w') as cachefile:
                json.dump(self.cache, cachefile)

        def probe(self):
            try:
                q_j = load_json(dlq_expiry_url(args))['value']
                old_count = self.cache.get(q_j['Name'])

                if old_count is None:
                    more = 0
                    msg = 'First check for DLQ'
                else:
                    assert isinstance(old_count, int)
                    more = q_j['MessageCount'] - old_count
                    if more == 0:
                        msg = 'No messages in'
                    elif more > 0:
                        msg = 'More messages in'
                    else:  # more < 0
                        msg = 'No more messages in'
                self.cache[q_j['Name']] = q_j['MessageCount']
                self.write_cache()
                return np.Metric(msg + ' %s' % q_j['Name'], more, context='dlq_expiry_check')
            except IOError as e:
                return np.Metric('Fetching network FAILED: ' + str(e), -1, context='dlq_expiry_check')
            except ValueError as e:
                return np.Metric('Decoding Json FAILED: ' + str(e), -1, context='dlq_expiry_check')
            except KeyError as e:
                return np.Metric('Getting Queue(s) FAILED: ' + str(e), -1, context='dlq_expiry_check')

    class ActiveMqDlqSummary(np.Summary):
        def ok(self, results):
            return super(ActiveMqDlqSummary, self).ok(results)

    np.Check(
        ActiveMqDlq(args.cache_dir),
        ActiveMqDlqScalarContext('dlq_expiry_check'),
        ActiveMqDlqSummary()
    ).main(timeout=get_timeout())


def add_warn_crit(parser, what, default=5):
    parser.add_argument('-w', '--warn',
                        metavar='WARN', type=int, default=default,
                        help='Warning if ' + what + ' is greater than or equal to. (default: %(default)s)')
    parser.add_argument('-c', '--crit',
                        metavar='CRIT', type=int, default=(default * 2),
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
    connection.add_argument('--url-tail', default='console/jolokia/read',
                            help='Jolokia URL tail part. (default: %(default)s)')
    connection.add_argument('-j', '--jolokia-url', help='''Override complete Jolokia URL.
                                (Default: "http://USER:PWD@HOST:PORT/URLTAIL/").
                                The parameters --user, --pwd, --host and --port are IGNORED
                                if this parameter is specified!
                                Please set this parameter carefully as it essential
                                for the program to work properly and is not validated.''')

    credentials = parser.add_argument_group('Credentials')
    credentials.add_argument('-u', '--user', default='admin',
                             help='Username for ActiveMQ admin account. (default: %(default)s)')
    credentials.add_argument('-p', '--pwd', default='admin',
                             help='Password for ActiveMQ admin account. (default: %(default)s)')

    subparsers = parser.add_subparsers()

    # Sub-Parser for broker property
    parser_broker_property = subparsers.add_parser('broker_property', help="""Request API with given broker property:
                                                   This mode queries the API with the given broker property.""")
    add_warn_crit(parser_broker_property, 'Property Threshold')
    parser_broker_property.add_argument('--property', required=True, help='Broker Property to request the API with')
    parser_broker_property.add_argument('--check', required=False, default=True,
                                        help='Whether or not to validate the result against the threshold values')
    # no additional arguments necessary
    parser_broker_property.set_defaults(func=broker_property)

    # Sub-Parser for objects
    parser_query_object = subparsers.add_parser('query_object', help="""Check QueueSize: 
                                        This mode checks the queue size of one or more queues on the ActiveMQ server.
                                        You can specify a queue name to check (even a pattern);
                                        see description of the 'queue' paramter for details.""")
    add_warn_crit(parser_query_object, 'Object Threshold')
    parser_query_object.add_argument('object', nargs='?', help='''Name of the Object that will be checked.
                                    If left empty, all Objects will be checked.
                                    This also can be a Unix shell-style Wildcard (much less powerful than a RegEx)
                                    where * and ? can be used.''')
    parser_query_object.add_argument('--check', required=False, default=True,
                                     help='Whether or not to validate the result against the threshold values')
    parser_query_object.set_defaults(func=query_object)

    # Sub-Parser for queue_size
    parser_queuesize = subparsers.add_parser('queue_size', help="""Check QueueSize: 
                        This mode checks the queue size of one or more queues on the ActiveMQ server.
                        You can specify a queue name to check (even a pattern);
                        see description of the 'queue' paramter for details.""")

    add_warn_crit(parser_queuesize, 'Property Threshold')
    parser_queuesize.add_argument('queue', nargs='?', help='''Name of the Queue that will be checked.
                                    This also can be a Unix shell-style Wildcard (much less powerful than a RegEx)
                                    where * and ? can be used.''')
    parser_queuesize.add_argument('--address', required=False,
                                  help='Name of the Address of the Queue that will be checked.')
    parser_queuesize.add_argument('--type', required=False, default="anycast",
                                  help='Type of the Queue that will be checked.')
    parser_queuesize.set_defaults(func=queue_size)

    # Sub-Parser for health
    parser_health = subparsers.add_parser('health', help="""Check Health: 
                                            This mode checks if the broker's started status is 'True'.""")
    # no additional arguments necessary
    parser_health.set_defaults(func=broker_health)

    # Sub-Parser for exists
    parser_exists = subparsers.add_parser('exists', help="""Check Exists: 
                                        This mode checks if a Queue with the given name exists.
                                        If a Queue with this name exist, this mode yields OK.""")
    parser_exists.add_argument('--queue', required=True,
                               help='Name of the Queue that will be checked.')
    parser_exists.add_argument('--address', required=False,
                               help='Name of the Address of the Queue that will be checked.')
    parser_exists.add_argument('--type', required=False, default="anycast",
                               help='Type of the Queue that will be checked.')
    parser_exists.set_defaults(func=exists)

    # Sub-Parser for dlq/expiry
    parser_dlq_expiry = subparsers.add_parser('dlq_expiry_check', help="""Check DLQ (Dead Letter Queue) or ExpiryQueue:
                                        This mode checks if there are new messages in DLQ/ExpiryQueue.""")
    parser_dlq_expiry.add_argument('--address', required=False, default="DLQ", help="""Name of the Address 
                                                        of the Queue that will be checked. Default is DLQ""")
    parser_dlq_expiry.add_argument('--cache_dir',  required=False, default='~/.cache', help="""DLQ/ExpiryQueue 
                                                                      cache base directory. (default: %(default)s)""")
    add_warn_crit(parser_dlq_expiry, 'DLQ/ExpiryQueue Queue Size')
    parser_dlq_expiry.set_defaults(func=dlq_expiry)

    # Evaluate Arguments
    args = parser.parse_args()
    # call the determined function with the parsed arguments
    args.func(args)


if __name__ == '__main__':
    main()
