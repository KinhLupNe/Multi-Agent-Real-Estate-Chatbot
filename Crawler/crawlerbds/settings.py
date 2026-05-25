# Scrapy settings for batdongsan project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "crawlerbds"

SPIDER_MODULES = ["crawlerbds.spiders"]
NEWSPIDER_MODULE = "crawlerbds.spiders"

# Crawl responsibly by identifying yourself (and your website) on the user-agent
# USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
]
# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Spash server endpoint
#

ITEM_PIPELINES = {
    "crawlerbds.pipelines.TextNormalizePipeline": 100,
    "crawlerbds.pipelines.AddressCorretionPipeline": 200,
    "crawlerbds.pipelines.FieldsPreprocessPipeline": 300,
    "crawlerbds.pipelines.DuplicateCheckPipeline": 400,
    "crawlerbds.pipelines.PushToKafka": 500,
}

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 16


# Disable cookies (enabled by default)
COOKIES_ENABLED = True

# Disable Telnet Console (enabled by default)
# TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
}


SPIDER_MIDDLEWARES = {}


DOWNLOADER_MIDDLEWARES = {
    # "scrapy_cloudflare_middleware.middlewares.CloudFlareMiddleware": 560,  # cfscrape không tương thích urllib3>=2; bds.com.vn không cần bypass
    "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler": 570,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 580,
}


DOWNLOAD_TIMEOUT = 600  # Set the timeout to 300 seconds (default = 180)
DOWNLOAD_DELAY = 0.5  # Set the delay between requests to 0.5 seconds (default = 0)

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = True
# The initial download delay


LOG_FILE_APPEND = False

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

# Tls_client
CLIENT_IDENTIFIER = "chrome_112"
RANDOM_TLS_EXTENSION_ORDER = True
FORCE_HTTP1 = False  # default False
CATCH_PANICS = False  # default False
RAW_RESPONSE_TYPE = "HtmlResponse"  # HtmlResponse or TextResponse, default HtmlResponse
