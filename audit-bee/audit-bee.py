#!/usr/bin/python
"""
Audit bee
"""

import os
import sys
import time
import datetime
import pytz
import ConfigParser
import argparse
import socket
import MySQLdb as mdb
import simplejson
import urllib2
import dateutil.parser
import requests
from urlparse import urlparse
import types
from urllib2 import Request, urlopen, URLError, HTTPError
from simplemediawiki import MediaWiki
import re
sys.path.append('../lib')
from apiary import ApiaryBot


class AuditBee(ApiaryBot):

    def __init__(self):
        ApiaryBot.__init__(self)

        # Initialize stats
        self.stats['audit_count'] = 0
        self.stats['audit_success'] = 0
        self.stats['audit_failure'] = 0

        # Array to put the sites we are auditing into
        self.my_sites = []

        def get_args(self):
            parser = argparse.ArgumentParser(prog="Bumble Bee", description="retrieves usage and statistic information for WikiApiary")
            parser.add_argument("-s", "--segment", help="only work on websites in defined segment")
            parser.add_argument("--site", help="only work on this specific site id")
            parser.add_argument("-f", "--force", action="store_true", help="run regardless of when the last time data was updated")
            parser.add_argument("-d", "--debug", action="store_true", help="do not write any changes to wiki or database")
            parser.add_argument("--config", default="../apiary.cfg", help="use an alternative config file")
            parser.add_argument("-v", "--verbose", action="count", default=0, help="increase output verbosity")
            parser.add_argument("--version", action="version", version="%(prog)s 0.1")

            # All set, now get the arguments
            self.args = parser.parse_args()

    def update_audit_status(self, pagename):
        if self.args.verbose >= 2:
            print "%s audit completed, updating audit date." % pagename

        socket.setdefaulttimeout(30)
        c = self.apiary_wiki.call({
            'action': 'sfautoedit',
            'form': 'Website',
            'target': pagename,
            'Website[Audited]': 'Yes',
            'Website[Audited date]': time.strftime('%Y/%m/%d %I:%M:%S %p', time.gmtime()),
            'wpSummary': 'audited'})
        if self.args.verbose >= 3:
            print c

    def set_flag(self, site, name, value, comment):
        if self.args.verbose >= 2:
            print "%s setting %s to %s (%s)." % (site['pagename'], name, value, comment)

        property = "Website[%s]" % name
        socket.setdefaulttimeout(30)
        c = self.apiary_wiki.call({
            'action': 'sfautoedit',
            'form': 'Website',
            'target': site['pagename'],
            property: value,
            'wpSummary': comment})
        if self.args.verbose >= 3:
            print c

    def genericAPIAudit(self, site, qs):
        api_url = "%s%s" % (site['Has API URL'], qs)
        req = requests.get(api_url, allow_redirects=False, timeout=5).json()
        if req.status_code == 200:
            if 'error' in req:
                # We got a properly formatted error back, bail
                print "ERROR: Returned error"
                return (False, req)
        else:
            return (False, req)

        return (True, req)

    def auditGeneral(self, site):
        # Test the site to see if it will successfully respond to a request for general info
        qs = '?action=query&meta=siteinfo&siprop=general&format=json'

        (success, req) = self.genericAPIAudit(site, qs)

        # should return query -> general (dictionary)
        if 'query' in req:
            if 'extensions' in req['query']:
                if isinstance(req['query']['extensions'], types.ListType):
                    print "Found %d extensions." % len(req['query']['extensions'])
                return True
        else:
            print req

    def auditExtensions(self, site):
        # Test the site to see if it will successfully report the extensions it uses
        qs = '?action=query&meta=siteinfo&siprop=extensions&format=json'
        # should return query -> extensions (array)

        if site['Has API URL'] == '':
            # This requires the API, we cannot conduct this test
            return False

        api_url = "%s%s" % (site['Has API URL'], qs)
        req = requests.get(api_url, allow_redirects=False, timeout=5).json()

        if 'error' in req:
            # We got a properly formatted error back, bail
            print "ERROR: Returned error"
            return False

        if 'query' in req:
            if 'extensions' in req['query']:
                if isinstance(req['query']['extensions'], types.ListType):
                    print "Found %d extensions." % len(req['query']['extensions'])
                return True
        else:
            print req

    def auditSkins(self, site):
        # Test the site to see if it will report the skinds it uses
        # ?action=query&meta=siteinfo&siprop=skins&format=json
        # should return query -> skins (array)
        return True

    def auditStatistics(self, site):
        # Test to see if the site will respond for requests for statistics
        # ?action=query&meta=siteinfo&siprop=statistics&format=json
        # should return query -> statistics (dictionary)
        # OR
        # ?action=raw
        return True

    def auditSmwInfo(self, site):
        # Test the site to see if it will return SMW statistics
        # ?action=smwinfo&format=json
        # should return info -> propcount (dictionary)
        return True

    def auditSmwUsage(self, site):
        # Test the site to see if it has SMW usage turned on
        # ?action=parse&page=Project:SMWExtInfo&prop=text&disablepp=1&format=json
        # should return parse -> text -> * (string)
        return True

    def auditLogs(self, site):
        # Test the site to see if it will return requests for logs
        # ?action=query&list=logevents&format=json
        # should return api -> query -> logevents (array)
        return True

    def auditRc(self, site):
        # Test the site to see if it will report Recent Changes via API
        # ?action=query&list=recentchanges&format=json
        # should return api -> query -> recentchanges (array)
        return True

    def validateCollectionURL(self, site, URLKey):
        # parse the URL out, and then recombine it
        if URLKey not in site:
            # The key being requested is not defined
            print "We don't have a %s." % URLKey
            return False

        urlParts = urlparse(site[URLKey])
        if (urlParts[0] is not '') and (urlParts[1] is not '') and (urlParts[2] is not ''):
            urlRecombined = "%s://%s%s" % (urlParts.scheme, urlParts.netloc, urlParts.path)
        if urlRecombined != site[URLKey]:
            print "Validated %s of %s doesn't match provided %s. Update it!" % (URLKey, urlRecombined, site[URLKey])
        # Test the API URL for valid 200 response
        testRequest = requests.head(urlRecombined, allow_redirects=False, timeout=5)
        print "URL returned %d" % testRequest.status_code
        if testRequest.status_code == 200:
            # worked great
            return True
        elif testRequest.status_code == 301:
            # Permanent redirect, we should update the URL and test again
            return True
        else:
            print "API URL returned status %d" % testRequest.status_code
            return False

    def audit_site(self, site):
        # First, let's validate the URL's provided for the API and Special page
        # if these are bad, we shouldn't even try auditing. To do this we will
        self.validateCollectionURL(site, 'Has API URL')
        self.validateCollectionURL(site, 'Has statitics URL')

        # Run each audit test
        result = self.auditGeneral(site)
        result = self.auditExtensions(site)
        result = self.auditSkins(site)
        result = self.auditStatistics(site)
        result = self.auditSmwInfo(site)
        result = self.auditSmwUsage(site)
        result = self.auditLogs(site)
        result = self.auditRc(site)

        # if self.args.verbose >= 1:
        #     print "\n\nSite: ", site
        # data_url = site['Has API URL'] + "?action=query&meta=siteinfo&siprop=general&format=json"
        # if self.args.verbose >= 2:
        #     print "Pulling general info info from %s." % data_url
        # (success, data, duration) = self.pull_json(site, data_url, bot='Audit Bee')

        # audit_complete = False
        # audit_extensions_complete = False
        # do_audit_extensions = False

        # if success:
        #     if 'query' in data:
        #         do_audit_extensions = self.set_audit(site, data['query']['general'])
        #         audit_complete = True
        #     elif 'error' in data:
        #         if 'code' in data['error']:
        #             if data['error']['code'] == 'readapidenied':
        #                 # This website will not let us talk to it, defunct it.
        #                 self.set_flag(site['pagename'], 'Defunct', 'Yes', 'Marking defunct because readapidenied')
        #                 self.record_error(
        #                     site=site,
        #                     log_message="readapidenied, marking defunct",
        #                     log_type='warn',
        #                     log_severity='important',
        #                     log_bot='Audit Bee',
        #                     log_url=data_url
        #                 )
        #             else:
        #                 self.record_error(
        #                     site=site,
        #                     log_message="Returned error %s" % data['error']['code'],
        #                     log_type='warn',
        #                     log_severity='important',
        #                     log_bot='Audit Bee',
        #                     log_url=data_url
        #                 )
        #         else:
        #             self.record_error(
        #                 site=site,
        #                 log_message="An unknown error was returned from site info",
        #                 log_type='warn',
        #                 log_severity='important',
        #                 log_bot='Audit Bee',
        #                 log_url=data_url
        #             )
        #     else:
        #         self.record_error(
        #             site=site,
        #             log_message="Returned unexpected JSON while requesting general site info",
        #             log_type='warn',
        #             log_severity='important',
        #             log_bot='Audit Bee',
        #             log_url=data_url
        #         )

        # # Pull extension information for audit too!
        # if do_audit_extensions:
        #     data_url = site['Has API URL'] + "?action=query&meta=siteinfo&siprop=extensions&format=json"
        #     if self.args.verbose >= 2:
        #         print "Pulling extension info info from %s." % data_url
        #     (success, data, duration) = self.pull_json(site['pagename'], data_url, bot='Audit Bee')

        #     if success:
        #         if 'query' in data:
        #             self.set_audit_extensions(site, data['query']['extensions'])
        #             audit_extensions_complete = True
        #         else:
        #             self.record_error(
        #                 site=site,
        #                 log_message="Returned unexpected JSON while requesting extensions",
        #                 log_type='warn',
        #                 log_severity='important',
        #                 log_bot='Audit Bee',
        #                 log_url=data_url
        #             )

        # if (audit_complete):
        #     # Let's see if we need to update the Founded date
        #     my_query = ''.join([
        #         "[[%s]]" % site['pagename'],
        #         '|?Founded date'
        #     ])

        #     if self.args.verbose >= 3:
        #         print "Query: %s" % my_query

        #     socket.setdefaulttimeout(30)
        #     check_date = self.apiary_wiki.call({'action': 'ask', 'query': my_query})

        #     if self.args.verbose >= 3:
        #         print "Response: %s" % check_date

        #     if len(check_date['query']['results'][site['pagename']]['printouts']['Founded date']) > 0:
        #         update_founded_date = False
        #     else:
        #         update_founded_date = True

        #     if (update_founded_date):
        #         # ?action=query&prop=revisions&revids=1&rvprop=timestamp&format=json
        #         first_date_url = site['Has API URL'] + "?action=query&prop=revisions&revids=1&rvprop=timestamp&format=json"
        #         (success, first_change, duration) = self.pull_json(site, first_date_url, bot='Audit Bee')
        #         if success:
        #             try:
        #                 timestamp = first_change['query']['pages']['1']['revisions'][0]['timestamp']
        #                 # timestamp is ISO 8601 format
        #                 first_edit = dateutil.parser.parse(timestamp)
        #                 self.set_flag(site['pagename'], 'Founded date', first_edit.strftime('%Y/%m/%d %I:%M:%S %p'), 'Setting founded date to timestamp of first edit')
        #             except:
        #                 self.record_error(
        #                     site=site,
        #                     log_message="Failed to get timestamp of first revision to wiki.",
        #                     log_type='warn',
        #                     log_severity='important',
        #                     log_bot='Audit Bee',
        #                     log_url=first_date_url
        #                 )
        #         else:
        #             self.record_error(
        #                 site=site,
        #                 log_message="Failed to get timestamp for first edit.",
        #                 log_type='warn',
        #                 log_severity='important',
        #                 log_bot='Audit Bee',
        #                 log_url=first_date_url
        #             )
        #     else:
        #         if self.args.verbose >= 2:
        #             print "Date founded is already set, not checking."

        # if (audit_complete) and (do_audit_extensions == audit_extensions_complete):
        #     # Activate the site, but only if the site has not been audited before
        #     # if this is a re-audit, leave these flags alone.
        #     if not site['Is audited']:
        #         if not site['Is active']:
        #             if self.args.verbose >= 2:
        #                 print "Activating %s." % site['pagename']
        #             self.set_flag(site['pagename'], 'Active', 'Yes', "Activated.")

        #     self.stats['audit_success'] += 1
        # else:
        #     self.stats['audit_failure'] += 1

        # # Update audit status, wether success or failure
        # self.update_audit_status(site['pagename'])

    def get_audit_list(self, group, count=20):
        my_query = ''.join([
            # "[[Concept:%s]]" % group,
            '[[Has bot segment::1]]',
            '|?Has ID',
            '|?Has API URL',
            '|?Has statistics URL'
            '|?Collect general data',
            '|?Collect extension data',
            '|?Collect skin data',
            '|?Collect statistics via',
            '|?Collect semantic statistics',
            '|?Collect semantic usage',
            '|?Collect logs',
            '|?Collect recent changes',
            '|?Creation date',
            '|?Is audited',
            '|?Is active',
            '|sort=Creation date',
            '|order=asc',
            "|limit=%d" % count])

        if self.args.verbose >= 3:
            print "Query: %s" % my_query

        socket.setdefaulttimeout(30)
        sites = self.apiary_wiki.call({
            'action': 'ask',
            'query': my_query
        })

        if len(sites['query']['results']) > 0:
            for pagename, site in sites['query']['results'].items():
                if self.args.verbose >= 3:
                    print "Adding %s." % pagename

                # Initialize the flags but do it carefully in case there is no value in the wiki yet
                try:
                    collect_general_data = (site['printouts']['Collect general data'][0] == "t")
                except:
                    collect_general_data = False

                try:
                    collect_extension_data = (site['printouts']['Collect extension data'][0] == "t")
                except:
                    collect_extension_data = False

                try:
                    collect_skin_data = (site['printouts']['Collect skin data'][0] == "t")
                except:
                    collect_skin_data = False

                try:
                    collect_statistics = (site['printouts']['Collect statistics'][0] == "t")
                except:
                    collect_statistics = False

                try:
                    collect_semantic_statistics = (site['printouts']['Collect semantic statistics'][0] == "t")
                except:
                    collect_semantic_statistics = False

                try:
                    collect_semantic_usage = (site['printouts']['Collect semantic usage'][0] == "t")
                except:
                    collect_semantic_usage = False

                try:
                    collect_statistics_stats = (site['printouts']['Collect statistics stats'][0] == "t")
                except:
                    collect_statistics_stats = False

                try:
                    collect_logs = (site['printouts']['Collect logs'][0] == "t")
                except:
                    collect_logs = False

                try:
                    collect_recent_changes = (site['printouts']['Collect recent changes'][0] == "t")
                except:
                    collect_recent_changes = False

                try:
                    has_statistics_url = site['printouts']['Has statistics URL'][0]
                except:
                    has_statistics_url = None

                try:
                    has_api_url = site['printouts']['Has API URL'][0]
                except:
                    has_api_url = None

                self.my_sites.append({
                    'pagename': pagename,
                    'Has API URL': has_api_url,
                    'Has statistics URL': has_statistics_url,
                    'Creation date': site['printouts']['Creation date'][0],
                    'Has ID': int(site['printouts']['Has ID'][0]),
                    'Collect general data': collect_general_data,
                    'Collect extension data': collect_extension_data,
                    'Collect skin data': collect_skin_data,
                    'Collect statistics': collect_statistics,
                    'Collect semantic statistics': collect_semantic_statistics,
                    'Collect semantic usage': collect_semantic_usage,
                    'Collect statistics stats': collect_statistics_stats,
                    'Collect logs': collect_logs,
                    'Collect recent changes': collect_recent_changes,
                    'Is audited': (site['printouts']['Is audited'][0] == "t"),
                    'Is active': (site['printouts']['Is active'][0] == "t")
                })

    def main(self):
        # Track the time we started
        start_time = time.time()

        # Setup our connection to the wiki too
        self.connectwiki('Audit Bee')

        # We will be auditing multiple "groups". These match to Concepts in WikiApiary
        audit_groups = ['Websites never audited', 'Websites expired audit']

        for group in audit_groups:
            self.my_sites = []
            self.get_audit_list(group=group, count=20)
            # Did we get sites back?
            if len(self.my_sites) > 0:
                for site in self.my_sites:
                    self.stats['audit_count'] += 1
                    # try:
                    self.audit_site(site)
                    # except Exception, e:
                    #     # Master exception handler for anything that wasn't caught during audit
                    #     self.record_error(
                    #         site=site,
                    #         log_message="Unhandled exception %s." % e,
                    #         log_type='error',
                    #         log_severity='important',
                    #         log_bot='Audit Bee'
                    #     )

        if self.stats['audit_count'] > 0:
            # If we did any work, let's log it. If not, be silent
            duration = time.time() - start_time
            message = "Completed audit %d sites %d succeeded %d failed" % (self.stats['audit_count'], self.stats['audit_success'], self.stats['audit_failure'])
            # self.botlog(bot='Audit Bee', duration=float(duration), message=message)


# Run
if __name__ == '__main__':
    bee = AuditBee()
    bee.main()
