import unittest
import unittest.mock

import os
import copy
import yaml
import datetime

import service

class MockChoreRedis(object):

    def __init__(self, host, port, channel):

        self.host = host
        self.port = port
        self.channel = channel

        self.chores = {}
        self.nexted = []

    def get(self, node):

        if node in self.chores:
            return self.chores[node]

        return None

    def create(self, template, person, node):

        chore = copy.deepcopy(template)
        chore.update({
            "id": node,
            "person": person,
            "node": node
        })
        self.chores[node] = chore


class TestService(unittest.TestCase):

    @unittest.mock.patch.dict(os.environ, {
        "GOOGLE_CALENDAR": "people",
        "REDIS_HOST": "data.com",
        "REDIS_PORT": "667",
        "REDIS_CHANNEL": "stuff",
        "RANGE": "10",
        "SLEEP": "7"
    })
    @unittest.mock.patch("pi_k8s_fitches.chore_redis.ChoreRedis", MockChoreRedis)
    def setUp(self):

        self.daemon = service.Daemon()

    def test___init___(self):

        self.assertEqual(self.daemon.calendar, "people")
        self.assertEqual(self.daemon.chore_redis.host, "data.com")
        self.assertEqual(self.daemon.chore_redis.port, 667)
        self.assertEqual(self.daemon.chore_redis.channel, "stuff")
        self.assertEqual(self.daemon.range, 10)
        self.assertEqual(self.daemon.sleep, 7)
        self.assertIsNone(self.daemon.calendar_id)
        self.assertIsNone(self.daemon.calendar_api)

    @unittest.mock.patch("googleapiclient.discovery.build")
    @unittest.mock.patch("oauth2client.file.Storage")
    @unittest.mock.patch("httplib2.Http")
    def test_subscribe(self, mock_http, mock_storage, mock_build):

        mock_api = unittest.mock.MagicMock()
        mock_api.calendarList.return_value.list.return_value.execute.return_value.get.return_value = [
            {
                "summary": "people",
                "id": "peeps"
            },
            {
                "summary": "things",
                "id": "teeps"
            }
        ]
        mock_storage.return_value.get.return_value.authorize.return_value = "www"
        mock_http.return_value = "web"
        mock_build.return_value = mock_api

        self.daemon.subscribe()

        self.assertEqual(self.daemon.calendar_id, "peeps")
        mock_build.assert_called_once_with("calendar", "v3", http="www")
        mock_storage.assert_called_once_with('/opt/pi-k8s/token.json')
        mock_storage.return_value.get.return_value.authorize.assert_called_once_with("web")
        mock_api.calendarList.return_value.list.return_value.execute.return_value.get.assert_called_once_with("items", [])

    @unittest.mock.patch("service.datetime")
    def test_process(self, mock_datetime):

        mock_datetime.timedelta = datetime.timedelta
        mock_datetime.timezone = datetime.timezone
        mock_datetime.datetime.utcnow.return_value = datetime.datetime(2018, 12, 13, 14, 15, 16, tzinfo=datetime.timezone.utc)

        self.daemon.calendar_id = "peeps"
        self.daemon.calendar_api = unittest.mock.MagicMock()

        self.daemon.calendar_api.events.return_value.list.return_value.execute.return_value.get.return_value = [
            {
                "description": "nope"
            },
            {
                "description": yaml.dump({}, default_flow_style=False)
            },
            {
                "description": yaml.dump({
                    "person": "nope"
                }, default_flow_style=False)
            },
            {
                "id": "done",
                "description": yaml.dump({
                    "person": "yep",
                    "node": "already"
                }, default_flow_style=False)
            },
            {
                "id": "do",
                "description": yaml.dump({
                    "person": "dude",
                    "node": "room"
                }, default_flow_style=False)
            }
        ]
        self.daemon.chore_redis.chores = {
            "already": {
                "event_id": "done"
            }
        }

        self.daemon.process()

        self.assertEqual(self.daemon.chore_redis.chores, {
            "already": {
                "event_id": "done"
            },
            "room": {
                "id": "room",
                "event_id": "do",
                "person": "dude",
                "node": "room"
            }
        })
        self.daemon.calendar_api.events.return_value.list.assert_called_once_with(
            calendarId="peeps", 
            timeMin="2018-12-13T14:15:11+00:00Z", 
            timeMax="2018-12-13T14:15:21+00:00Z", 
            singleEvents=True
        )
        self.daemon.calendar_api.events.return_value.list.return_value.execute.return_value.get.assert_called_once_with("items", [])

    @unittest.mock.patch("googleapiclient.discovery.build")
    @unittest.mock.patch("oauth2client.file.Storage")
    @unittest.mock.patch("httplib2.Http")
    @unittest.mock.patch("service.datetime")
    @unittest.mock.patch("service.time.sleep")
    @unittest.mock.patch("traceback.format_exc")
    @unittest.mock.patch('builtins.print')
    def test_run(self, mock_print, mock_traceback, mock_sleep, mock_datetime, mock_http, mock_storage, mock_build):

        mock_api = unittest.mock.MagicMock()
        mock_api.calendarList.return_value.list.return_value.execute.return_value.get.return_value = [
            {
                "summary": "people",
                "id": "peeps"
            }
        ]
        mock_api.events.return_value.list.return_value.execute.return_value.get.return_value = [
            {
                "id": "do",
                "description": yaml.dump({
                    "person": "dude",
                    "node": "room"
                }, default_flow_style=False)
            }
        ]
        mock_build.return_value = mock_api

        mock_datetime.timedelta = datetime.timedelta
        mock_datetime.timezone = datetime.timezone
        mock_datetime.datetime.utcnow.return_value = datetime.datetime(2018, 12, 13, 14, 15, 16, tzinfo=datetime.timezone.utc)

        mock_sleep.side_effect = [None, Exception("whoops"), Exception("whoops")]
        mock_traceback.side_effect = ["spirograph", Exception("doh")]

        self.assertRaisesRegex(Exception, "doh", self.daemon.run)

        self.assertEqual(self.daemon.chore_redis.chores, {
            "room": {
                "id": "room",
                "event_id": "do",
                "person": "dude",
                "node": "room"
            }
        })
        mock_print.assert_has_calls([
            unittest.mock.call("whoops"),
            unittest.mock.call("spirograph"),
            unittest.mock.call("whoops")
        ])
