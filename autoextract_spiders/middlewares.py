from fake_useragent import UserAgent
from scrapy import signals
from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware


class RandomUserAgentMiddleware(UserAgentMiddleware):

    @classmethod
    def from_crawler(cls, crawler):
        user_agent, random_type = crawler.settings['USER_AGENT'], None
        if crawler.settings.get('FAKEUSERAGENT_ENABLED'):
            random_type = crawler.settings.get('FAKEUSERAGENT_TYPE', 'random')
        o = cls(user_agent, random_type=random_type)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def __init__(self, user_agent='Scrapy', random_type=None):
        self.default_user_agent = user_agent
        self.random_type = random_type
        if self.random_type:
            self.user_agent_helper = UserAgent(fallback=user_agent)

    @property
    def user_agent(self):
        if self.random_type:
            return getattr(self.user_agent_helper, self.random_type)
        return self.default_user_agent
