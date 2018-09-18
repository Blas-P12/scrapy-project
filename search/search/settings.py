# Scrapy settings for search project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/topics/settings.html
#

import scrapy

BOT_NAME = 'search'

SPIDER_MODULES = ['search.spiders']
NEWSPIDER_MODULE = 'search.spiders'
ITEM_PIPELINES = ['search.pipelines.URLsPipeline']
#LOG_STDOUT = True
LOG_ENABLED = False
#LOG_FILE = "search_log.out"
LOG_LEVEL=scrapy.log.WARNING
DUPEFILTER_CLASS = 'scrapy.dupefilter.BaseDupeFilter'

HTTPCACHE_STORAGE = 'scrapy.contrib.downloadermiddleware.httpcache.FilesystemCacheStorage'
HTTPCACHE_POLICY = 'scrapy.contrib.httpcache.RFC2616Policy'
#HTTPCACHE_POLICY = 'SamsungCachePolicy.SamsungCachePolicy'

DOWNLOAD_DELAY = 0.05
#TODO
#COOKIES_ENABLED = False

# $HOME/.scrapy_cache
import os
homedir = os.getenv("HOME")
HTTPCACHE_DIR = homedir + '/.scrapy_cache'
#HTTPCACHE_STORAGE = 'scrapy.contrib.httpcache.DbmCacheStorage'
#HTTPCACHE_ENABLED = True

# use proxy
DOWNLOADER_MIDDLEWARES = {
    'scrapy.contrib.downloadermiddleware.httpproxy.HttpProxyMiddleware': 110,
    'search.middlewares.ProxyMiddleware': 100,
}

# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.57 Safari/537.36"
