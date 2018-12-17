"""
Main module for daemon
"""

import os
import time
import datetime
import traceback

import yaml
import redis
import googleapiclient.discovery
import httplib2
import oauth2client.file
import pi_k8s_fitches.chore_redis


class Daemon(object):
    """
    Main class for daemon
    """

    def __init__(self):

        self.calendar = os.environ['GOOGLE_CALENDAR']
        self.chore_redis = pi_k8s_fitches.chore_redis.ChoreRedis(
            host=os.environ['REDIS_HOST'],
            port=int(os.environ['REDIS_PORT']),
            channel=os.environ['REDIS_CHANNEL']
        )
        self.range = int(os.environ['RANGE'])
        self.sleep = int(os.environ['SLEEP'])
        self.calendar_id = None
        self.calendar_api = None

    def subscribe(self):
        """
        Subscribes to the the calendar events
        """

        self.calendar_api = googleapiclient.discovery.build(
            'calendar', 
            'v3', 
            http=oauth2client.file.Storage('/opt/pi-k8s/token.json').get().authorize(httplib2.Http())
        )

        for calendar in self.calendar_api.calendarList().list().execute().get('items', []):
            if calendar["summary"] == self.calendar:
                self.calendar_id = calendar["id"]

    def process(self):
        """
        Processes events within the range, create chores if needed
        """

        before = datetime.datetime.utcnow() - datetime.timedelta(seconds=self.range/2)
        after = before + datetime.timedelta(seconds=self.range)

        for event in self.calendar_api.events().list(
            calendarId=self.calendar_id, 
            timeMin=before.isoformat() + 'Z', 
            timeMax=after.isoformat() + 'Z', 
            singleEvents=True
        ).execute().get('items', []):

            template = yaml.load(event["description"])

            if not isinstance(template, dict) or "person" not in template or "node" not in template:
                continue

            chore = self.chore_redis.get(template["node"])

            if chore is not None and event["id"] == chore["event_id"]:
                continue
            
            template["event_id"] = event["id"]

            self.chore_redis.create(template, template["person"], template["node"])

    def run(self):
        """
        Runs the daemon
        """

        self.subscribe()

        while True:
            try:
                self.process()
                time.sleep(self.sleep)
            except Exception as exception:
                print(str(exception))
                print(traceback.format_exc())