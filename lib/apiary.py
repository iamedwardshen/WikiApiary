"""
Base class for all WikiApiary bots. To make another bot, create a new class derived
from this class.

Jamie Thingelstad <jamie@thingelstad.com>
http://wikiapiary.com/wiki/User:Thingles
http://thingelstad.com/
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
import random
import re
from urllib2 import Request, urlopen, URLError, HTTPError
from simplemediawiki import MediaWiki


class ApiaryBot:

    args = []
    config = []
    apiary_wiki = []
    apiary_db = []
    stats = {}
    edit_token = ''

    def __init__(self):
        # Get configuration settings
        self.get_config(self.args.config)
        # Connect to the database
        self.connectdb()

    def get_config(self, config_file='../apiary.cfg'):
        try:
            self.config = ConfigParser.ConfigParser()
            self.config.read(config_file)
        except IOError:
            print "Cannot open %s." % config_file

    def filter_illegal_chars(self, pre_filter):
        # Utility function to make sure that strings are okay for page titles
        return re.sub(r'[#<>\[\]\|{}]', '', pre_filter).replace('=', '-')

    def sqlutcnow(self):
        now = datetime.datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        now = now.replace(microsecond=0)
        return now.strftime('%Y-%m-%d %H:%M:%S')

    def pull_json(self, site, data_url, bot='Bumble Bee'):
        socket.setdefaulttimeout(10)

        # Get JSON data via API and return the JSON structure parsed
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
                log_message="%s" % str(e),
                log_type='info',
                log_severity='normal',
                log_bot='Bumble Bee',
                log_url=data_url
            )
            return False, None, None
        else:
            # It all worked!
            try:
                # Clean the returned string before we parse it, sometimes there are junky error messages
                # from PHP in here, or simply a newline that shouldn't be present
                # The regex here is really simple, but it seems to work fine.
                ret_string = f.read()
                json_match = re.search(r"({.*})", ret_string, flags=re.MULTILINE)
                if json_match.group(1) is not None:
                    # Found JSON block
                    data = simplejson.loads(json_match.group(1))
                else:
                    # No JSON content in the response
                    self.record_error(
                        site=site,
                        log_message="No JSON found",
                        log_type='info',
                        log_severity='normal',
                        log_bot='Bumble Bee',
                        log_url=data_url
                    )
                    return False, None, None
            except Exception, e:
                self.record_error(
                    site=site,
                    log_message="%s" % str(e),
                    log_type='info',
                    log_severity='normal',
                    log_bot='Bumble Bee',
                    log_url=data_url
                )
                return False, None, None
            return True, data, duration

    def runSql(self, sql_command):
        if self.args.verbose >= 3:
            print "SQL: %s" % sql_command
        try:
            cur = self.apiary_db.cursor()
            cur.execute(sql_command)
            cur.close()
            self.apiary_db.commit()
            return True, cur.rowcount
        except Exception, e:
            print "Exception generated while running SQL command."
            print "Command: %s" % sql_command
            print "Exception: %s" % e
            return False, 0

    def record_error(self, site, log_message, log_type='info', log_severity='normal', log_bot=None, log_url=None):
        if 'pagename' not in site:
            if 'Has name' in site:
                site['pagename'] = site['Has name']

        if self.args.verbose >= 2:
            print "New log message for %s" % site['pagename']

        if self.args.verbose >= 1:
            print log_message

        if log_bot is None:
            log_bot = "null"
        else:
            log_bot = "'%s'" % log_bot

        if log_url is None:
            log_url = "null"
        else:
            log_url = "'%s'" % log_url

        temp_sql = "INSERT  apiary_website_logs (website_id, log_date, website_name, log_type, log_severity, log_message, log_bot, log_url) "
        temp_sql += "VALUES (%d, \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", %s, %s)" % (
            site['Has ID'],
            self.sqlutcnow(),
            site['pagename'],
            log_type,
            log_severity,
            log_message,
            log_bot,
            log_url
        )

        self.runSql(temp_sql)

    def connectdb(self):
        # Setup our database connection
        # Use the account that can also insert and delete from the database
        self.apiary_db = mdb.connect(
            host=self.config.get('ApiaryDB', 'hostname'),
            db=self.config.get('ApiaryDB', 'database'),
            user=self.config.get('ApiaryDB RW', 'username'),
            passwd=self.config.get('ApiaryDB RW', 'password'),
            charset='utf8')

    def connectwiki(self, bot_name):
        self.apiary_wiki = MediaWiki(self.config.get('WikiApiary', 'API'))
        self.apiary_wiki.login(self.config.get(bot_name, 'Username'), self.config.get(bot_name, 'Password'))
        # We need an edit token
        c = self.apiary_wiki.call({'action': 'query', 'titles': 'Foo', 'prop': 'info', 'intoken': 'edit'})
        self.edit_token = c['query']['pages']['-1']['edittoken']

    def botlog(self, bot, message, type='info', duration=0):
        if self.args.verbose >= 1:
            print message

        temp_sql = "INSERT  apiary_bot_log (log_date, log_type, bot, duration, message) "
        temp_sql += "VALUES (\"%s\", \"%s\", \"%s\", %f, \"%s\")" % (self.sqlutcnow(), type, bot, duration, message)

        self.runSql(temp_sql)
