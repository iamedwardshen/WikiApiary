#! /usr/bin/env python

"""
Bumble Bee is responsible for collecting statistics and other information from
sites registered on WikiApiary. See http://wikiapiary.com/wiki/User:Bumble_Bee
for more information.

Jamie Thingelstad <jamie@thingelstad.com>
http://wikiapiary.com/wiki/User:Thingles
http://thingelstad.com/
"""

import os
import sys
import time
import datetime
import argparse
import socket
import simplejson
import urllib2
from urllib2 import Request, urlopen, URLError, HTTPError
from simplemediawiki import MediaWiki
import re
import HTMLParser
import BeautifulSoup
import operator
import urlparse
import pygeoip
sys.path.append('../lib')
from apiary import ApiaryBot


class BumbleBee(ApiaryBot):
    """Bot that collects statistics for sites."""

    def __init__(self):
        ApiaryBot.__init__(self)

        # Get command line options
        self.get_args()

        # Initialize stats
        self.stats['statistics'] = 0
        self.stats['smwinfo'] = 0
        self.stats['smwusage'] = 0
        self.stats['general'] = 0
        self.stats['extensions'] = 0
        self.stats['skins'] = 0
        self.stats['skippedstatistics'] = 0
        self.stats['skippedgeneral'] = 0

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

    def get_websites(self, segment, site):
        filter_string = ""
        if site is not None:
            if self.args.verbose >= 1:
                print "Processing site %d." % int(site)
            filter_string = "[[Has ID::%d]]" % int(site)
        elif segment is not None:
            if self.args.verbose >= 1:
                print "Only retrieving segment %d." % int(self.args.segment)
            filter_string = "[[Has bot segment::%d]]" % int(self.args.segment)

        # Build query for sites
        my_query = ''.join([
            '[[Category:Website]]',
            '[[Is defunct::False]]',
            '[[Is active::True]]',
            filter_string,
            '|?Has API URL',
            '|?Has statistics URL',
            '|?Check every',
            '|?Creation date',
            '|?Has ID',
            '|?In error',
            '|?Collect general data',
            '|?Collect extension data',
            '|?Collect skin data',
            '|?Collect statistics',
            '|?Collect semantic statistics',
            '|?Collect semantic usage',
            '|?Collect logs',
            '|?Collect recent changes',
            '|?Collect statistics stats',
            '|sort=Creation date',
            '|order=asc',
            '|limit=1000'])
        if self.args.verbose >= 3:
            print "Query: %s" % my_query
        sites = self.apiary_wiki.call({'action': 'ask', 'query': my_query})

        # We could just return the raw JSON object from the API, however instead we are going to clean it up into an
        # easier to deal with array of dictionary objects.
        # To keep things sensible, we'll use the same name as the properties
        i = 0
        if len(sites['query']['results']) > 0:
            my_sites = []
            for pagename, site in sites['query']['results'].items():
                i += 1
                if self.args.verbose >= 3:
                    print "[%d] Adding %s." % (i, pagename)

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
                    has_statistics_url = ''

                try:
                    has_api_url = site['printouts']['Has API URL'][0]
                except:
                    has_api_url = ''

                if has_statistics_url.find('wikkii.com') > 0:
                    # Temporary filter out all Farm:Wikkii sites
                    if self.args.verbose >= 2:
                        print "Skipping %s (%s)" % (pagename, site['fullurl'])
                else:
                    my_sites.append({
                        'pagename': pagename,
                        'fullurl': site['fullurl'],
                        'Has API URL': has_api_url,
                        'Has statistics URL': has_statistics_url,
                        'Check every': int(site['printouts']['Check every'][0]),
                        'Creation date': site['printouts']['Creation date'][0],
                        'Has ID': int(site['printouts']['Has ID'][0]),
                        'In error': (site['printouts']['In error'][0] == "t"),  # Boolean fields we'll convert from the strings we get back to real booleans
                        'Collect general data': collect_general_data,
                        'Collect extension data': collect_extension_data,
                        'Collect skin data': collect_skin_data,
                        'Collect statistics': collect_statistics,
                        'Collect semantic statistics': collect_semantic_statistics,
                        'Collect semantic usage': collect_semantic_usage,
                        'Collect statistics stats': collect_statistics_stats,
                        'Collect logs': collect_logs,
                        'Collect recent changes': collect_recent_changes
                    })

            return my_sites
        else:
            raise Exception("No sites were returned to work on.")

    def get_status(self, site):
        """
        get_status will query the website_status table in ApiaryDB. It makes the decision if new
        data should be retrieved for a given website. Two booleans are returned, the first to
        tell if new statistics information should be requested and the second to pull general information.
        """
        # Get the timestamps for the last statistics and general pulls
        cur = self.apiary_db.cursor()
        temp_sql = "SELECT last_statistics, last_general, check_every_limit FROM website_status WHERE website_id = %d" % site['Has ID']
        cur.execute(temp_sql)
        rows_returned = cur.rowcount

        if rows_returned == 1:
            # Let's see if it's time to pull information again
            data = cur.fetchone()
            cur.close()

            (last_statistics, last_general, check_every_limit) = data[0:3]
            if self.args.verbose >= 3:
                print "last_stats: %s" % last_statistics
                print "last_general: %s" % last_general
                print "check_every_limit: %s" % check_every_limit

            #TODO: make this check the times!
            last_statistics_struct = time.strptime(str(last_statistics), '%Y-%m-%d %H:%M:%S')
            last_general_struct = time.strptime(str(last_general), '%Y-%m-%d %H:%M:%S')

            stats_delta = (time.mktime(time.gmtime()) - time.mktime(last_statistics_struct)) / 60
            general_delta = (time.mktime(time.gmtime()) - time.mktime(last_general_struct)) / 60

            if self.args.verbose >= 2:
                print "Delta from checks: stats %s general %s" % (stats_delta, general_delta)

            (check_stats, check_general) = (False, False)
            if stats_delta > (site['Check every'] + random.randint(0, 15))  and stats_delta > check_every_limit:    # Add randomness to keep checks spread around
                check_stats = True
            else:
                if self.args.verbose >= 2:
                    print "Skipping stats..."
                self.stats['skippedstatistics'] += 1

            if general_delta > ((24 + random.randint(0, 24)) * 60):   # General checks are always bound to 24 hours, plus a random offset to keep checks evenly distributed
                check_general = True
            else:
                if self.args.verbose >= 2:
                    print "Skipping general..."
                self.stats['skippedgeneral'] += 1

            return (check_stats, check_general)

        elif rows_returned == 0:
            cur.close()
            # This website doesn't have a status, so we should check everything
            if self.args.verbose >= 3:
                print "website has never been checked before"
            return (True, True)

        else:
            raise Exception("Status check returned multiple rows.")

    def update_status(self, site, checktype):
        # Update the website_status table
        my_now = self.sqlutcnow()

        if checktype == "statistics":
            temp_sql = "UPDATE website_status SET last_statistics = '%s' WHERE website_id = %d" % (my_now, site['Has ID'])

        if checktype == "general":
            temp_sql = "UPDATE website_status SET last_general = '%s' WHERE website_id = %d" % (my_now, site['Has ID'])

        (success, rows_affected) = self.runSql(temp_sql)

        if rows_affected == 0:
            # No rows were updated, this website likely didn't exist before, so we need to insert the first time
            if self.args.verbose >= 2:
                print "No website_status record exists for ID %d, creating one" % site['Has ID']
            temp_sql = "INSERT website_status (website_id, last_statistics, last_general, check_every_limit) "
            temp_sql += "VALUES (%d, \"%s\", \"%s\", %d)" % (site['Has ID'], my_now, my_now, 240)
            self.runSql(temp_sql)

    def parse_version(self, t):
        ver = {}

        if self.args.verbose >= 3:
            print "Getting version details for %s" % t

        try:
            # Do we have a x.y.z
            y = re.findall(r'^(?:(\d+)\.)?(?:(\d+)\.?)?(?:(\d+)\.?)?(?:(\d+)\.?)?', t)
            if y:
                if len(y[0][0]) > 0:
                    ver['major'] = y[0][0]
                if len(y[0][1]) > 0:
                    ver['minor'] = y[0][1]
                if len(y[0][2]) > 0:
                    ver['bugfix'] = y[0][2]

            if not ver.get('major', None):
                # Do we have a YYYY-MM-DD
                if re.match(r'\d{4}-\d{2}-\d{2}', t):
                    y = re.findall(r'(\d+)', t)
                    (ver['major'], ver['minor'], ver['bugfix']) = y

            if not ver.get('major', None):
                # Do we have a YYYYMMDD
                if re.match(r'\d{4}\d{2}\d{2}', t):
                    y = re.findall(r'(\d{4})(\d{2})(\d{2})', t)
                    (ver['major'], ver['minor'], ver['bugfix']) = y[0]

            # Do we have a flag
            y = re.match(r'.*(alpha|beta|wmf|CLDR|MLEB|stable).*', t)
            if y:
                ver['flag'] = y.group(1)
        except Exception, e:
            self.botlog(bot='Bumble Bee', type="warn", message="Exception %s while parsing version string %s" % (e, t))

        if self.args.verbose >= 2:
            print "Version details: ", ver

        return ver

    def record_statistics(self, site, method):
        if method == 'API':
            # Go out and get the statistic information
            data_url = site['Has API URL'] + '?action=query&meta=siteinfo&siprop=statistics&format=json'
            if self.args.verbose >= 2:
                print "Pulling statistics info from %s." % data_url
            (status, data, duration) = self.pull_json(site, data_url)
        elif method == 'Statistics':
            # Get stats the old fashioned way
            data_url = site['Has statistics URL']
            if "?" in data_url:
                data_url += "&action=raw"
            else:
                data_url += "?action=raw"
            if self.args.verbose >= 2:
                print "Pulling statistics from %s." % data_url

            # This is terrible and should be put into pull_json somewhow
            socket.setdefaulttimeout(15)

            # Get CSV data via raw Statistics call
            req = urllib2.Request(data_url)
            req.add_header('User-Agent', self.config.get('Bumble Bee', 'User-Agent'))
            opener = urllib2.build_opener()

            try:
                t1 = datetime.datetime.now()
                f = opener.open(req)
                duration = (datetime.datetime.now() - t1).total_seconds()
            except Exception, e:
                self.record_error(
                    site=site,
                    log_message="%s" % e,
                    log_type='error',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                status = False
            else:
                # Create an object that is the same as that returned by the API
                ret_string = f.read()
                ret_string = ret_string.strip()
                if re.match(r'(\w+=\d+)\;?', ret_string):
                    # The return value looks as we expected
                    status = True
                    data = {}
                    data['query'] = {}
                    data['query']['statistics'] = {}
                    items = ret_string.split(";")
                    for item in items:
                        (name, value) = item.split("=")
                        try:
                            # Convert the value to an int, if this fails we skip it
                            value = int(value)
                            if name == "total":
                                name = "pages"
                            if name == "good":
                                name = "articles"
                            if self.args.verbose >= 3:
                                print "Transforming %s to %s" % (name, value)
                            data['query']['statistics'][name] = value
                        except:
                            if self.args.verbose >= 3:
                                print "Illegal value '%s' for %s." % (value, name)
                else:
                    status = False # The result didn't match the pattern expected
                    self.record_error(
                        site=site,
                        log_message="Unexpected response to statistics call",
                        log_type='error',
                        log_severity='normal',
                        log_bot='Bumble Bee',
                        log_url=data_url
                    )
                    if self.args.verbose >= 3:
                        print "Result from statistics was not formatted as expected:\n%s" % ret_string

        ret_value = True
        if status:
            # Record the new data into the DB
            if self.args.verbose >= 2:
                print "JSON: %s" % data
                print "Duration: %s" % duration

            if 'query' in data:
                # Record the data received to the database
                sql_command = """
                    INSERT INTO statistics
                        (website_id, capture_date, response_timer, articles, jobs, users, admins, edits, activeusers, images, pages, views)
                    VALUES
                        (%s, '%s', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """

                data = data['query']['statistics']
                if 'articles' in data:
                        articles = "%s" % data['articles']
                else:
                        articles = 'null'
                if 'jobs' in data:
                        jobs = "%s" % data['jobs']
                else:
                        jobs = 'null'
                if 'users' in data:
                        users = "%s" % data['users']
                else:
                        users = 'null'
                if 'admins' in data:
                        admins = "%s" % data['admins']
                else:
                        admins = 'null'
                if 'edits' in data:
                        edits = "%s" % data['edits']
                else:
                        edits = 'null'
                if 'activeusers' in data:
                        if data['activeusers'] < 0:
                            data['activeusers'] = 0
                        activeusers = "%s" % data['activeusers']
                else:
                        activeusers = 'null'
                if 'images' in data:
                        images = "%s" % data['images']
                else:
                        images = 'null'
                if 'pages' in data:
                        pages = "%s" % data['pages']
                else:
                        pages = 'null'
                if 'views' in data:
                        views = "%s" % data['views']
                else:
                        views = 'null'

                sql_command = sql_command % (
                    site['Has ID'],
                    self.sqlutcnow(),
                    duration,
                    articles,
                    jobs,
                    users,
                    admins,
                    edits,
                    activeusers,
                    images,
                    pages,
                    views)

                self.runSql(sql_command)
                self.stats['statistics'] += 1
            else:
                self.record_error(
                    site=site,
                    log_message='Statistics returned unexpected JSON.',
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                ret_value = False

        else:
            if self.args.verbose >= 3:
                print "Did not receive valid data from %s" % (data_url)
            ret_value = False

        # Update the status table that we did our work!
        self.update_status(site, 'statistics')
        return ret_value

    def record_smwusage(self, site):
        # Get the extended SMW usage
        data_url = site['Has API URL'] + '?action=parse&page=Project:SMWExtInfo&prop=text&disablepp=1&format=json'
        if self.args.verbose >= 2:
            print "Pulling semantic usage info from %s." % data_url
        (status, data, duration) = self.pull_json(site, data_url)

        if status:
            try:
                data_block = data['parse']['text']['*']
                data_soup = BeautifulSoup.BeautifulSoup(data_block)
                json_block = data_soup.find("div", {"id": "wikiapiary-semantic-usage-data"})
                json_data = simplejson.loads(json_block.text)
            except Exception, e:
                self.record_error(
                    site=site,
                    log_message="Semantic usage failed parsing: %s" % e,
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                return False

            sql = """INSERT INTO smwextinfo
        (website_id, capture_date, response_timer,
         query_count, query_pages, query_concepts, query_pageslarge,
         size1, size2, size3, size4, size5, size6, size7, size8, size9, size10plus,
         format_broadtable, format_csv, format_category, format_count, format_dsv, format_debug, format_embedded,
         format_feed, format_json, format_list, format_ol, format_rdf, format_table, format_template, format_ul)
    VALUES
        ( %d, '%s', %f,
          %d, %d, %d, %d,
          %d, %d, %d, %d, %d, %d, %d, %d, %d, %d,
          %d, %d, %d, %d, %d, %d, %d,
          %d, %d, %d, %d, %d, %d, %d, %d)"""

            sql_command = sql % (
                site['Has ID'],
                self.sqlutcnow(),
                duration,
                json_data['smwqueries']['count'],
                json_data['smwqueries']['pages'],
                json_data['smwqueries']['concepts'],
                json_data['smwqueries']['pageslarge'],
                json_data['smwquerysizes']['size-1'],
                json_data['smwquerysizes']['size-2'],
                json_data['smwquerysizes']['size-3'],
                json_data['smwquerysizes']['size-4'],
                json_data['smwquerysizes']['size-5'],
                json_data['smwquerysizes']['size-6'],
                json_data['smwquerysizes']['size-7'],
                json_data['smwquerysizes']['size-8'],
                json_data['smwquerysizes']['size-9'],
                json_data['smwquerysizes']['size-10plus'],
                json_data['smwformats']['broadtable'],
                json_data['smwformats']['csv'],
                json_data['smwformats']['category'],
                json_data['smwformats']['count'],
                json_data['smwformats']['dsv'],
                json_data['smwformats']['debug'],
                json_data['smwformats']['embedded'],
                json_data['smwformats']['feed'],
                json_data['smwformats']['json'],
                json_data['smwformats']['list'],
                json_data['smwformats']['ol'],
                json_data['smwformats']['rdf'],
                json_data['smwformats']['table'],
                json_data['smwformats']['template'],
                json_data['smwformats']['ul'])

            self.runSql(sql_command)
            self.stats['smwusage'] += 1

        else:
            if self.args.verbose >= 3:
                print "Did not receive valid data from %s" % (data_url)
            return False

    def record_smwinfo(self, site):
        # Go out and get the statistic information
        data_url = site['Has API URL'] + ''.join([
            '?action=smwinfo',
            '&info=propcount%7Cusedpropcount%7Cdeclaredpropcount%7Cproppagecount%7Cquerycount%7Cquerysize%7Cconceptcount%7Csubobjectcount',
            '&format=json'])
        if self.args.verbose >= 2:
            print "Pulling SMW info from %s." % data_url
        (status, data, duration) = self.pull_json(site, data_url)

        ret_value = True
        if status:
            # Record the new data into the DB
            if self.args.verbose >= 2:
                print "JSON: %s" % data
                print "Duration: %s" % duration

            if 'info' in data:
                # Record the data received to the database
                sql_command = """
                    INSERT INTO smwinfo
                        (website_id, capture_date, response_timer, propcount, proppagecount, usedpropcount, declaredpropcount,
                            querycount, querysize, conceptcount, subobjectcount)
                    VALUES
                        (%d, '%s', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """

                if 'propcount' in data['info']:
                        propcount = data['info']['propcount']
                else:
                        propcount = 'null'
                if 'proppagecount' in data['info']:
                        proppagecount = data['info']['proppagecount']
                else:
                        proppagecount = 'null'
                if 'usedpropcount' in data['info']:
                        usedpropcount = data['info']['usedpropcount']
                else:
                        usedpropcount = 'null'
                if 'declaredpropcount' in data['info']:
                        declaredpropcount = data['info']['declaredpropcount']
                else:
                        declaredpropcount = 'null'

                # Catch additional results returned in SMW 1.9
                if 'querycount' in data['info']:
                    querycount = data['info']['querycount']
                else:
                    querycount = 'null'
                if 'querysize' in data['info']:
                    querysize = data['info']['querysize']
                else:
                    querysize = 'null'
                if 'conceptcount' in data['info']:
                    conceptcount = data['info']['conceptcount']
                else:
                    conceptcount = 'null'
                if 'subobjectcount' in data['info']:
                    subobjectcount = data['info']['subobjectcount']
                else:
                    subobjectcount = 'null'

                sql_command = sql_command % (
                    site['Has ID'],
                    self.sqlutcnow(),
                    duration,
                    propcount,
                    proppagecount,
                    usedpropcount,
                    declaredpropcount,
                    querycount,
                    querysize,
                    conceptcount,
                    subobjectcount)

                self.runSql(sql_command)
                self.stats['smwinfo'] += 1
            else:
                self.record_error(
                    site=site,
                    log_message='SMWInfo returned unexpected JSON.',
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                ret_value = False

        else:
            if self.args.verbose >= 3:
                print "Did not receive valid data from %s" % (data_url)
            ret_value = False

        # Update the status table that we did our work!
        # TODO: Commenting out. There is a bug that if this updates at the same time as the previous one
        # there is no change to the row, and my check for rows_affected in update_status will
        # not work as intended. Going to assume that smwinfo slaves off of regular statistics.
        #self.update_status(site, 'statistics')
        return ret_value

    def ProcessMultiprops(self, site_id, key, value):
        # Here we deal with properties that change frequently and we care about all of them.
        # For example, dbversion in a wiki farm will often have multiple values
        # and we will get different values each time, rotating between a set.
        # This function will take the value and return a more complex data structure.

        # First update the timestamp for seeing the current name/value
        cur = self.apiary_db.cursor()
        temp_sql = "UPDATE apiary_multiprops SET last_date=\'%s\', occurrences = occurrences + 1 WHERE website_id = %d AND t_name = \'%s\' AND t_value = \'%s\'" % (
            self.sqlutcnow(),
            site_id,
            key,
            value)
        if self.args.verbose >= 3:
            print "SQL Debug: %s" % temp_sql
        cur.execute(temp_sql)
        rows_returned = cur.rowcount

        # No rows returned, we need to create this value
        if rows_returned == 0:
            temp_sql = "INSERT apiary_multiprops (website_id, t_name, t_value, first_date, last_date, occurrences) VALUES (%d, \'%s\', \'%s\', \'%s\', \'%s\', %d)" % (
                site_id,
                key,
                value,
                self.sqlutcnow(),
                self.sqlutcnow(),
                1)
            if self.args.verbose >= 3:
                print "SQL Debug: %s" % temp_sql
            cur.execute(temp_sql)

        # Now build the return value
        multivalue = ""
        temp_sql = "SELECT t_value, last_date, occurrences FROM apiary_multiprops WHERE website_id = %d AND last_date > \'%s\' ORDER BY occurrences DESC" % (
            site_id,
            '2013-04-26 18:23:01')
        cur.execute(temp_sql)
        rows = cur.fetchall()
        for row in rows:
            if len(multivalue) > 0:
                multivalue += ","
            multivalue += "%s" % row[0]

        return multivalue

    def build_general_template(self, site_id, x, server):

        # Some keys we do not want to store in WikiApiary
        ignore_keys = ['time', 'fallback', 'fallback8bitEncoding']
        # Some keys we turn into more readable names for using inside of WikiApiary
        key_names = {
            'dbtype': 'Database type',
            'dbversion': 'Database version',
            'generator': 'MediaWiki version',
            'lang': 'Language',
            'timezone': 'Timezone',
            'timeoffset': 'Timeoffset',
            'sitename': 'Sitename',
            'rights': 'Rights',
            'phpversion': 'PHP Version',
            'phpsapi': 'PHP Server API',
            'wikiid': 'Wiki ID'
        }

        template_block = "<noinclude>{{Notice bot owned page}}</noinclude><includeonly>"

        template_block += "{{General siteinfo\n"
        template_block += "|HTTP server=%s\n" % (server)

        # Loop through all the keys provided and create the template block
        for key in x:
            # Make sure we aren't ignoring this key
            if key not in ignore_keys:
                # If we have a name for this key use that
                name = key_names.get(key, key)
                value = x[key]

                # For some items we may need to do some preprocessing
                if isinstance(value, basestring):
                    # A pipe will break the template, try HTML entity encoding it instead
                    value = value.replace('|', '&#124;')
                if key == 'lang':
                    # Make sure language is all lowercase, and try to standardize structure
                    value = value.lower().replace('_', '-').replace(' ', '-')
                if key == 'sitename':
                    # Sometimes a : appears in sitename and messes up semantics
                    # Try using an HTML entity instead
                    value = value.replace(':', '&#58;')
                if key == 'dbversion':
                    value = self.ProcessMultiprops(site_id, key, value)

                template_block += "|%s=%s\n" % (name, value)

        template_block += "}}\n</includeonly>\n"

        return template_block

    def BuildNetworkTemplate(self, hostname):
        template_block = "\n<includeonly>"
        template_block += "{{Network info\n"

        gi = pygeoip.GeoIP('../vendor/GeoLiteCity.dat')
        data = gi.record_by_name(hostname)

        for val in data:
            template_block += "|%s=%s\n" % (val, data[val])

        template_block += "}}\n</includeonly>\n"

        return template_block

    def record_general(self, site):
        data_url = site['Has API URL'] + "?action=query&meta=siteinfo&siprop=general&format=json"
        if self.args.verbose >= 2:
            print "Pulling general info info from %s." % data_url
        (success, data, duration) = self.pull_json(site, data_url)
        ret_value = True
        if success:
            # Successfully pulled data
            if 'query' in data:
                datapage = "%s/General" % site['pagename']
                template_block = self.build_general_template(site['Has ID'], data['query']['general'], '')

                # Shoe horning in the Geo data
                hostname = urlparse.urlparse(site['Has API URL']).hostname
                network_template = self.BuildNetworkTemplate(hostname)
                template_block += network_template

                socket.setdefaulttimeout(30)
                c = self.apiary_wiki.call({'action': 'edit', 'title': datapage, 'text': template_block, 'token': self.edit_token, 'bot': 'true'})
                if self.args.verbose >= 3:
                    print c
                self.stats['general'] += 1
            else:
                self.record_error(
                    site=site,
                    log_message='Returned unexpected JSON when general info.',
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                ret_value = False

        # Update the status table that we did our work! It doesn't matter if this was an error.
        self.update_status(site, 'general')
        return ret_value

    def build_extensions_template(self, ext_obj):
        h = HTMLParser.HTMLParser()

        # Some keys we do not want to store in WikiApiary
        ignore_keys = ['descriptionmsg']
        # Some keys we turn into more readable names for using inside of WikiApiary
        key_names = {
            'author': 'Extension author',
            'name': 'Extension name',
            'version': 'Extension version',
            'type': 'Extension type',
            'url': 'Extension URL'
        }

        template_block = "<noinclude>{{Notice bot owned page}}</noinclude><includeonly>"

        for x in ext_obj:
            if 'name' in x:
                template_block += "{{Extension in use\n"

                for item in x:
                    if item not in ignore_keys:

                        name = key_names.get(item, item)
                        value = x[item]

                        if item == 'name':
                            # Sometimes people make the name of the extension a hyperlink using
                            # wikitext links and this makes things ugly. So, let's detect that if present.
                            if re.match(r'\[(http[^\s]+)\s+([^\]]+)\]', value):
                                (possible_url, value) = re.findall(r'\[(http[^\s]+)\s+([^\]]+)\]', value)[0]
                                # If a URL was given in the name, and not given as a formal part of the
                                # extension definition (yes, this happens) then add this to the template
                                # it is up to the template to decide what to do with this
                                template_block += "|URL Embedded in name=%s" % possible_url

                            value = self.filter_illegal_chars(value)
                            value = value.replace('&nbsp;', ' ')

                        if item == 'version':
                            # Breakdown the version information for more detailed analysis
                            ver_details = self.parse_version(value)
                            if 'major' in ver_details:
                                template_block += "|Extension version major=%s\n" % ver_details['major']
                            if 'minor' in ver_details:
                                template_block += "|Extension version minor=%s\n" % ver_details['minor']
                            if 'bugfix' in ver_details:
                                template_block += "|Extension version bugfix=%s\n" % ver_details['bugfix']
                            if 'flag' in ver_details:
                                template_block += "|Extension version flag=%s\n" % ver_details['flag']

                        if item == 'author':
                            # Authors can have a lot of junk in them, wikitext and such.
                            # We'll try to clean that up.

                            # Wikilinks with names
                            # "[[Foobar | Foo Bar]]"
                            value = re.sub(r'\[\[.*\|(.*)\]\]', r'\1', value)
                            # Simple Wikilinks
                            value = re.sub(r'\[\[(.*)\]\]', r'\1', value)
                            # Hyperlinks as wikiext
                            # "[https://www.mediawiki.org/wiki/User:Jeroen_De_Dauw Jeroen De Dauw]"
                            value = re.sub(r'\[\S+\s+([^\]]+)\]', r'\1', value)
                            # Misc text
                            value = re.sub(r'\sand\s', r', ', value)
                            value = re.sub(r'\.\.\.', r'', value)
                            value = re.sub(r'&nbsp;', r' ', value)
                            # Lastly, there could be HTML encoded stuff in these
                            value = h.unescape(value)

                        if item == 'url':
                            # Seems some people really really love protocol agnostic URL's
                            # We detect them and add a generic http: protocol to them
                            if re.match(r'^\/\/', value):
                                value = 'http:' + value

                        template_block += "|%s=%s\n" % (name, value)

                template_block += "}}\n"

        template_block += "</includeonly>"

        return template_block

    def record_extensions(self, site):
        data_url = site['Has API URL'] + "?action=query&meta=siteinfo&siprop=extensions&format=json"
        if self.args.verbose >= 2:
            print "Pulling extensions from %s." % data_url
        (success, data, duration) = self.pull_json(site, data_url)
        ret_value = True
        if success:
            # Successfully pulled data
            if 'query' in data:
                datapage = "%s/Extensions" % site['pagename']
                template_block = self.build_extensions_template(data['query']['extensions'])
                socket.setdefaulttimeout(30)
                c = self.apiary_wiki.call({'action': 'edit', 'title': datapage, 'text': template_block, 'token': self.edit_token, 'bot': 'true'})
                if self.args.verbose >= 3:
                    print c
                self.stats['extensions'] += 1
            else:
                self.record_error(
                    site=site,
                    log_message='Returned unexpected JSON when requesting extension data.',
                    log_type='warn',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                ret_value = False
        return ret_value

    def build_skins_template(self, ext_obj):

        # Some keys we do not want to store in WikiApiary
        ignore_keys = []
        # Some keys we turn into more readable names for using inside of WikiApiary
        key_names = {
            '*': 'Skin name',
            'code': 'Skin code',
            'default': 'Default skin',
            'unusable': 'Skipped skin'
        }

        template_block = "<noinclude>{{Notice bot owned page}}</noinclude><includeonly>"

        # Skins are returned in random order so we need to sort them before
        # making the template, otherwise we generate a lot of edits
        # that are just different ordering
        skins_sorted = sorted(ext_obj, key=operator.itemgetter('*'))

        for x in skins_sorted:
            if '*' in x:
                # Start the template instance
                template_block += "{{Skin in use\n"
                for item in x:
                    # Loop through all the items in the skin data and build the instance
                    if item not in ignore_keys:
                        name = key_names.get(item, item)
                        value = x[item]

                        if item == '*':
                            value = self.filter_illegal_chars(value)

                        if item == 'default':
                            # This parameter won't appear unless it is true
                            value = True

                        if item == 'unusable':
                            # This paramter won't appear unless it is true
                            value = True

                        template_block += "|%s=%s\n" % (name, value)

                # Now end the template instance
                template_block += "}}\n"

        template_block += "</includeonly>"

        return template_block

    def record_skins(self, site):
        data_url = site['Has API URL'] + "?action=query&meta=siteinfo&siprop=skins&format=json"
        if self.args.verbose >= 2:
            print "Pulling skin info from %s." % data_url
        (success, data, duration) = self.pull_json(site, data_url)
        ret_value = True
        if success:
            # Successfully pulled data
            if 'query' in data:
                datapage = "%s/Skins" % site['pagename']
                template_block = self.build_skins_template(data['query']['skins'])
                socket.setdefaulttimeout(30)
                c = self.apiary_wiki.call({'action': 'edit', 'title': datapage, 'text': template_block, 'token': self.edit_token, 'bot': 'true'})
                if self.args.verbose >= 3:
                    print c
                self.stats['skins'] += 1
            else:
                self.record_error(
                    site=site,
                    log_message='Returned unexpected JSON when requesting skin data.',
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                ret_value = False
        return ret_value

    def main(self):
        if self.args.site is not None:
            message = "Starting processing for site %d." % int(self.args.site)
        elif self.args.segment is not None:
            message = "Starting processing for segement %d." % int(self.args.segment)
        else:
            message = "Starting processing for all websites."
        self.botlog(bot='Bumble Bee', message=message)

        # Record time at beginning
        start_time = time.time()

        # Setup our connection to the wiki too
        self.connectwiki('Bumble Bee')

        # Get list of websites to work on
        sites = self.get_websites(self.args.segment, self.args.site)

        i = 0
        for site in sites:
            i += 1
            if self.args.verbose >= 1:
                print "\n\n%d: Processing %s (ID %d)" % (i, site['pagename'], site['Has ID'])
            if site['In error'] and self.args.verbose >= 1:
                print "Site %s (ID %d) is flagged in error." % (site['pagename'], site['Has ID'])
            req_statistics = False
            req_general = False
            if self.args.force:
                (req_statistics, req_general) = (True, True)
            else:
                (req_statistics, req_general) = self.get_status(site)

            # Put this section in a try/catch so that we can proceed even if a single site causes a problem
            try:
                process = "unknown"
                if req_statistics:
                    if site['Collect statistics']:
                        process = "collect statistics (API)"
                        status = self.record_statistics(site, 'API')
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                    if site['Collect statistics stats']:
                        process = "collect statistics (Statistics)"
                        status = self.record_statistics(site, 'Statistics')
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                    if site['Collect semantic statistics']:
                        process = "collect semantic statistics"
                        status = self.record_smwinfo(site)
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                    if site['Collect semantic usage']:
                        process = "collect semantic usage"
                        status = self.record_smwusage(site)
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                if req_general:
                    time.sleep(2)  # TODO: this is dumb, doing to not trigger a problem with update_status again due to no rows being modified if the timestamp is the same. Forcing the timestamp to be +1 second
                    if site['Collect general data']:
                        process = "collect general data"
                        status = self.record_general(site)
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                    if site['Collect extension data']:
                        process = "collect extension data"
                        status = self.record_extensions(site)
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
                    if site['Collect skin data']:
                        process = "collect skin data"
                        status = self.record_skins(site)
                        if site['In error'] and status:
                            site['In error'] = False
                            self.clear_error(site['pagename'])
            except Exception, e:
                self.record_error(
                    site=site,
                    log_message='Unhandled exception %s during %s' % (str(e), process),
                    log_type='error',
                    log_severity='normal',
                    log_bot='Bumble Bee'
                )

        duration = time.time() - start_time
        if self.args.segment is not None:
            message = "Completed processing for segment %d." % int(self.args.segment)
        else:
            message = "Completed processing for all websites."
        message += " Processed %d websites." % i
        message += " Counters statistics %d smwinfo %d smwusage %d general %d extensions %d skins %d skipped_stats: %d skipped_general: %d" % (
            self.stats['statistics'], self.stats['smwinfo'], self.stats['smwusage'], self.stats['general'],
            self.stats['extensions'], self.stats['skins'], self.stats['skippedstatistics'], self.stats['skippedgeneral'])
        self.botlog(bot='Bumble Bee', duration=float(duration), message=message)


# Run
if __name__ == '__main__':
    bee = BumbleBee()
    bee.main()
