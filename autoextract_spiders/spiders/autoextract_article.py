import feedparser
from w3lib.html import strip_html5_whitespace
from scrapy.http import Request, HtmlResponse, XmlResponse

from .util import is_valid_url
from .crawler_spider import CrawlerSpider


class ArticleAutoExtract(CrawlerSpider):
    name = 'articles'
    page_type = 'article'

    frontera_settings = {
        'HCF_PRODUCER_FRONTIER': 'autoextract',
        'HCF_PRODUCER_SLOT_PREFIX': 'articles',
        'HCF_PRODUCER_NUMBER_OF_SLOTS': 1,
        'HCF_PRODUCER_BATCH_SIZE': 100,

        'HCF_CONSUMER_FRONTIER': 'autoextract',
        'HCF_CONSUMER_SLOT': 'articles0',
        'HCF_CONSUMER_MAX_REQUESTS': 100,
    }

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.main_callback = spider.parse_source
        spider.main_errback = spider.errback_source
        return spider

    def parse_source(self, response: HtmlResponse):
        """
        Parse a seed URL.
        """
        if not isinstance(response, HtmlResponse):
            self.logger.warning('Invalid Source response: %s', response)
            self.crawler.stats.inc_value('error/invalid_source_response')
            return

        feed_urls = self.get_feed_urls(response)
        if not feed_urls:
            self.logger.info('No feed found for URL: <%s>', response.url)

        # Initial request to the Feed URLs. Sent as normal request.
        for feed_url in feed_urls:
            self.crawler.stats.inc_value('sources/rss')
            meta = {'source_url': response.meta['source_url'], 'feed_url': feed_url}
            self.crawler.stats.inc_value('x_request/feeds')
            yield Request(
                feed_url,
                meta=meta,
                callback=self.parse_feed,
                errback=self.errback_feed,
                dont_filter=True)

        # Cycle and follow all the rest of the links
        yield from self._requests_to_follow(response)

    def errback_source(self, failure):
        """ Seed URL request error """
        self.crawler.stats.inc_value('error/failed_source_request')

    def get_feed_urls(self, response):
        """ Find all RSS or Atom feeds from a page """
        feed_urls = set()

        for link in response.xpath('//link[@type]'):
            link_type = strip_html5_whitespace(link.attrib['type'])
            link_href = strip_html5_whitespace(link.attrib.get('href', ''))
            if link_href:
                link_href = response.urljoin(link_href)
                rss_url = atom_url = None
                if 'rss+xml' in link_type:
                    rss_url = link_href
                elif 'atom+xml' in link_type:
                    atom_url = link_href
                feed_url = rss_url or atom_url
                if feed_url:
                    feed_urls.add(feed_url)

        if not feed_urls:
            for link in response.xpath('//a/@href').get():
                link_href = strip_html5_whitespace(link)
                if link_href.endswith('rss.xml'):
                    feed_url = response.urljoin(link_href)
                    feed_urls.add(feed_url)

        return feed_urls

    def parse_feed(self, response: XmlResponse):
        """
        Parse a feed XML.
        """
        if not isinstance(response, XmlResponse):
            self.logger.warning('Invalid Feed response: %s', response)
            self.crawler.stats.inc_value('error/invalid_feed_response')
            return
        feed = feedparser.parse(response.text)
        if not feed:
            self.crawler.stats.inc_value('error/rss_initially_empty')
            return

        seen = set()
        for entry in feed.get('entries', []):
            url = strip_html5_whitespace(entry.get('link'))
            if not is_valid_url(url):
                self.logger.warning('Ignoring invalid article URL: %s', url)
                continue
            if url not in seen:
                seen.add(url)

        if not seen:
            self.crawler.stats.inc_value('error/rss_finally_empty')
            return

        self.logger.info('Links extracted from <%s> feed = %d', response.url, len(seen))
        source_url = response.meta['source_url']
        feed_url = response.url

        for url in seen:
            self.crawler.stats.inc_value('links/rss')
            # Make a request to fetch the full page HTML
            # Risk of being banned
            self.crawler.stats.inc_value('x_request/discovery')
            yield Request(url,
                          meta={'source_url': source_url, 'feed_url': feed_url},
                          callback=self.parse_page,
                          errback=self.errback_page,
                          dont_filter=True)

    def errback_feed(self, failure):
        """ Feed XML request error """
        self.crawler.stats.inc_value('error/failed_feed_request')
