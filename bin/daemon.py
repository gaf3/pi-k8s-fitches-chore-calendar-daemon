#!/usr/bin/env python

import shutil
import service

shutil.copy("/etc/pi-k8s/token.json", "/opt/pi-k8s/token.json")
service.Daemon().run()
