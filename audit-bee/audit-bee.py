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

    def update_audit_status(self, pagename):
        self.stats['audit_success'] += 1
        # Audit completed
        if self.args.verbose >= 2:
            print "%s audit completed, updating audit status." % pagename

        socket.setdefaulttimeout(30)
        c = self.apiary_wiki.call({
            'action': 'sfautoedit',
            'form': 'Website',
            'target': pagename,
            'Website[Audited]': 'Yes',
            'Website[Audited date]': time.strftime('%Y/%m/%d %I:%M:%S %p', time.gmtime()),
            'wpSummary': 'Audit completed.'})
        if self.args.verbose >= 3:
            print c

    def set_flag(self, pagename, name, value, comment):
        if self.args.verbose >= 2:
            print "%s setting %s to %s (%s)." % (pagename, name, value, comment)

        property = "Website[%s]" % name
        socket.setdefaulttimeout(30)
        c = self.apiary_wiki.call({
            'action': 'sfautoedit',
            'form': 'Website',
            'target': pagename,
            property: value,
            'wpSummary': comment})
        if self.args.verbose >= 3:
            print c

    def set_audit_extensions(self, site, extensions):
        for extension in extensions:
            # Semantic statistics requires Semantic MediaWiki 1.6 or later.
            if extension.get('name', "") == 'Semantic MediaWiki':
                match = re.search(r'(\d+)\.(\d+)', extension['version'])
                (smw_version_major, smw_version_minor) = (int(match.group(1)), int(match.group(2)))

                if (smw_version_major >= 1) and (smw_version_minor >= 6) and (site[1]['printouts']['Collect semantic statistics'][0] == "f"):
                    self.set_flag(site[0], 'Collect semantic statistics', 'Yes', "Enabling statistics collection for Semantic MediaWiki %d.%d." % (smw_version_major, smw_version_minor))
                if (smw_version_major >= 1) and (smw_version_minor < 6) and (site[1]['printouts']['Collect semantic statistics'][0] == "t"):
                    self.set_flag(site[0], 'Collect semantic statistics', 'Yes', "Disabling statistics collection for Semantic MediaWiki %d.%d." % (smw_version_major, smw_version_minor))

    def set_audit(self, site, data):
        # Get the major and minor version numbers of MediaWiki
        match = re.search(r'\s(\d+)\.(\d+)', data['generator'])
        if match != None:
            (mw_version_major, mw_version_minor) = (int(match.group(1)), int(match.group(2)))

            if self.args.verbose >= 2:
                print "Website: %s  Generator: %s  Major: %d  Minor: %d" % (site[0], data['generator'], mw_version_major, mw_version_minor)

            # General data requires MediaWiki 1.8 or later.
            if (mw_version_major >= 1) and (mw_version_minor >= 8) and (site[1]['printouts']['Collect general data'][0] == "f"):
                self.set_flag(site[0], 'Collect general data', 'Yes', "MediaWiki %d.%d supports general collection" % (mw_version_major, mw_version_minor))

            # Extension data requires MediaWiki 1.14 or later.
            if (mw_version_major >= 1) and (mw_version_minor >= 14) and (site[1]['printouts']['Collect extension data'][0] == "f"):
                self.set_flag(site[0], 'Collect extension data', 'Yes', "Enabling extension collection for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))
            if (mw_version_major >= 1) and (mw_version_minor < 14) and (site[1]['printouts']['Collect extension data'][0] == "t"):
                self.set_flag(site[0], 'Collect extension data', 'No', "Disabling extensions collection for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))

            # Skin data requires MediaWiki 1.18 or later.
            if (mw_version_major >= 1) and (mw_version_minor >= 18) and (site[1]['printouts']['Collect skin data'][0] == "f"):
                self.set_flag(site[0], 'Collect skin data', 'Yes', "Enabling skin collection for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))
            if (mw_version_major >= 1) and (mw_version_minor < 18) and (site[1]['printouts']['Collect skin data'][0] == "t"):
                self.set_flag(site[0], 'Collect skin data', 'No', "Disabling skin collection for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))

            # General statistics requires MediaWiki 1.11 or later.
            if (mw_version_major >= 1) and (mw_version_minor >= 11) and (site[1]['printouts']['Collect statistics'][0] == "f"):
                self.set_flag(site[0], 'Collect statistics', 'Yes', "Enabling statistics for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))
            if (mw_version_major >= 1) and (mw_version_minor < 11) and (site[1]['printouts']['Collect statistics'][0] == "t"):
                self.set_flag(site[0], 'Collect statistics', 'No', "Disabling statistics for MediaWiki %d.%d." % (mw_version_major, mw_version_minor))

            # Return if extension data is available to check as well
            if (mw_version_major >= 1) and (mw_version_minor >= 14):
                return True
            else:
                return False

        else:
            # Unable to determine the version of MediaWiki. This is probably because the
            # wiki has been altered to hide its version.
            if self.args.verbose >= 2:
                print "%s returnd version %s which cannot be parsed." % (site[0], data['generator'])
            self.record_error(
                site=site[1]['printouts'],
                log_message="Unable to determine version from %s. Auditing without confirming any flags. Operator please check." % data['generator'],
                log_type='info',
                log_severity='normal',
                log_bot='Bumble Bee'
            )
            return False

    def audit_site(self, site):
        if self.args.verbose >= 1:
            print "\n\nSite: ", site
        data_url = site[1]['printouts']['Has API URL'][0] + "?action=query&meta=siteinfo&siprop=general&format=json"
        if self.args.verbose >= 2:
            print "Pulling general info info from %s." % data_url
        (success, data, duration) = self.pull_json(site, data_url, bot='Audit Bee')

        audit_complete = False
        audit_extensions_complete = False
        do_audit_extensions = False

        if success:
            if 'query' in data:
                do_audit_extensions = self.set_audit(site, data['query']['general'])
                audit_complete = True
            elif 'error' in data:
                if 'code' in data['error']:
                    if data['error']['code'] == 'readapidenied':
                        # This website will not let us talk to it, defunct it.
                        self.set_flag(site[0], 'Defunct', 'Yes', 'Marking defunct because readapidenied')
                        self.record_error(
                            site=site[1]['printouts'],
                            log_message="readapidenied, marking defunct",
                            log_type='warn',
                            log_severity='important',
                            log_bot='Audit Bee',
                            log_url=data_url
                        )
                    else:
                        self.record_error(
                            site=site[1]['printouts'],
                            log_message="Returned error %s" % data['error']['code'],
                            log_type='warn',
                            log_severity='important',
                            log_bot='Audit Bee',
                            log_url=data_url
                        )
                else:
                    self.record_error(
                        site=site[1]['printouts'],
                        log_message="An unknown error was returned from site info",
                        log_type='warn',
                        log_severity='important',
                        log_bot='Audit Bee',
                        log_url=data_url
                    )
            else:
                self.record_error(
                    site=site[1]['printouts'],
                    log_message="Returned unexpected JSON while requesting general site info",
                    log_type='warn',
                    log_severity='important',
                    log_bot='Audit Bee',
                    log_url=data_url
                )

        # Pull extension information for audit too!
        if do_audit_extensions:
            data_url = site[1]['printouts']['Has API URL'][0] + "?action=query&meta=siteinfo&siprop=extensions&format=json"
            if self.args.verbose >= 2:
                print "Pulling extension info info from %s." % data_url
            (success, data, duration) = self.pull_json(site[0], data_url, bot='Audit Bee')

            if success:
                if 'query' in data:
                    self.set_audit_extensions(site, data['query']['extensions'])
                    audit_extensions_complete = True
                else:
                    self.record_error(
                        site=site,
                        log_message="Returned unexpected JSON while requesting extensions",
                        log_type='warn',
                        log_severity='important',
                        log_bot='Audit Bee',
                        log_url=data_url
                    )

        if (audit_complete):
            # Let's see if we need to update the Founded date
            my_query = ''.join([
                "[[%s]]" % site[0],
                '|?Founded date'
            ])

            if self.args.verbose >= 3:
                print "Query: %s" % my_query

            socket.setdefaulttimeout(30)
            check_date = self.apiary_wiki.call({'action': 'ask', 'query': my_query})

            if self.args.verbose >= 3:
                print "Response: %s" % check_date

            if len(check_date['query']['results'][site[0]]['printouts']['Founded date']) > 0:
                update_founded_date = False
            else:
                update_founded_date = True

            if (update_founded_date):
                # ?action=query&prop=revisions&revids=1&rvprop=timestamp&format=json
                first_date_url = site[1]['printouts']['Has API URL'][0] + "?action=query&prop=revisions&revids=1&rvprop=timestamp&format=json"
                (success, first_change, duration) = self.pull_json(site, first_date_url, bot='Audit Bee')
                if success:
                    try:
                        timestamp = first_change['query']['pages']['1']['revisions'][0]['timestamp']
                        # timestamp is ISO 8601 format
                        first_edit = dateutil.parser.parse(timestamp)
                        self.set_flag(site[0], 'Founded date', first_edit.strftime('%Y/%m/%d %I:%M:%S %p'), 'Setting founded date to timestamp of first edit')
                    except:
                        self.record_error(
                            site=site[1]['printouts'],
                            log_message="Failed to get timestamp of first revision to wiki.",
                            log_type='warn',
                            log_severity='important',
                            log_bot='Audit Bee',
                            log_url=first_date_url
                        )
                else:
                    self.record_error(
                        site=site[1]['printouts'],
                        log_message="Failed to get timestamp for first edit.",
                        log_type='warn',
                        log_severity='important',
                        log_bot='Audit Bee',
                        log_url=first_date_url
                    )
            else:
                if self.args.verbose >= 2:
                    print "Date founded is already set, not checking."

        if (audit_complete) and (do_audit_extensions == audit_extensions_complete):
            # Activate the site, but only if the site has not been audited before
            # if this is a re-audit, leave these flags alone.
            if site[1]['printouts']['Is audited'][0] == "f":
                if site[1]['printouts']['Is active'][0] == "f":
                    if self.args.verbose >= 2:
                        print "Activating %s." % site[0]
                    self.set_flag(site[0], 'Active', 'Yes', "Activated.")

            # Update audit status
            self.update_audit_status(site[0])
        else:
            self.stats['audit_failure'] += 1

    def get_audit_list(self, group, count=20):
        my_query = ''.join([
            "[[Concept:%s]]" % group,
            '|?Has API URL',
            '|?Collect general data',
            '|?Collect extension data',
            '|?Collect skin data',
            '|?Collect statistics',
            '|?Collect semantic statistics',
            '|?Is audited',
            '|?Is active',
            '|?In error',
            '|sort=Creation date',
            '|order=rand',
            "|limit=%d" % count])

        if self.args.verbose >= 3:
            print "Query: %s" % my_query

        socket.setdefaulttimeout(30)
        sites = self.apiary_wiki.call({'action': 'ask', 'query': my_query})

        if len(sites['query']['results']) > 0:
            return len(sites['query']['results']), sites['query']['results'].items()
        else:
            return 0, None

    def main(self):
        start_time = time.time()

        # Setup our connection to the wiki too
        self.connectwiki('Audit Bee')

        # Do never audited first
        (site_count, sites) = self.get_audit_list(group='Websites never audited', count=20)
        if site_count > 0:
            for site in sites:
                self.stats['audit_count'] += 1
                try:
                    self.audit_site(site)
                except Exception, e:
                    print "Exception %s during audit of %s." % (e, site)

        # Do re-audits
        (site_count, sites) = self.get_audit_list(group='Websites expired audit', count=20)
        if site_count > 0:
            for site in sites:
                self.stats['audit_count'] += 1
                try:
                    self.audit_site(site)
                except Exception, e:
                    print "Exception %s during audit of %s." % (e, site)

        duration = time.time() - start_time
        if self.stats['audit_count'] > 0:
            message = "Completed audit %d sites  %d succeeded  %d failed" % (self.stats['audit_count'], self.stats['audit_success'], self.stats['audit_failure'])
            self.botlog(bot='Audit Bee', duration=float(duration), message=message)


# Run
if __name__ == '__main__':
    bee = AuditBee()
    bee.main()
