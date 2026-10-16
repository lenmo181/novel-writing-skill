#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dify 插件入口。"""
from dify_plugin import DifyPluginEnv, Plugin

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=180))

if __name__ == "__main__":
    plugin.run()
