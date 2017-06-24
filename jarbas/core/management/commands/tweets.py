import logging
import re

import twitter
from django.conf import settings
from django.core.management.base import BaseCommand

from jarbas.core.models import Reimbursement, Tweet


log = logging.getLogger('django')


class Command(BaseCommand):
    help = 'Find out and save links to @RosieDaSerenata tweets'

    def handle(self, *args, **options):
        credentials = (
            settings.TWITTER_CONSUMER_KEY,
            settings.TWITTER_CONSUMER_SECRET,
            settings.TWITTER_ACCESS_TOKEN,
            settings.TWITTER_ACCESS_SECRET
        )

        # check for credentials
        if not all(credentials):
            log.warning('No Twitter API consumer key and/or secret set.')
            return

        # create API and pick the most recent Twiiter to limit the query
        self.api = twitter.Api(*credentials, sleep_on_rate_limit=True)
        self.latest_tweet = Tweet.objects.first()

        # persist tweet status in the database
        for status, document_id in self.document_ids:

            # skip if reimbursement does not exist
            reimbursement = Reimbursement.objects.get(document_id=document_id)
            if not reimbursement:
                continue

            # skip if status is already related to that reimbursement
            try:
                current_tweet = reimbursement.tweet
            except Reimbursement.tweet.RelatedObjectDoesNotExist:
                pass
            else:
                if current_tweet and current_tweet.status == status:
                    continue

            self.save_tweet(reimbursement, status)

    @property
    def tweets(self):
        kwargs = dict(
            screen_name='RosieDaSerenata',
            count=200,  # this is the maximum suported by Twitter API
            include_rts=False,
            exclude_replies=True
        )

        if self.latest_tweet:
            kwargs['since_id'] = self.latest_tweet.status

        yield from self.api.GetUserTimeline(**kwargs)

    @property
    def urls(self):
        for tweet in self.tweets:
            yield from ((tweet.id, url.expanded_url) for url in tweet.urls)

    @staticmethod
    def get_document_id(url):
        match = re.search(r'documentId\/(?P<document_id>\d*)', url)
        if match:
            return match.group('document_id')

    @property
    def document_ids(self):
        for tweet_id, url in self.urls:
            document_id = self.get_document_id(url)
            if document_id:
                yield tweet_id, document_id

    @staticmethod
    def save_tweet(reimbursement, status):
        reimbursement.tweet = Tweet(reimbursement=reimbursement, status=status)
        reimbursement.save()

        msg = 'Document #{} linked to {}'
        args = (reimbursement.document_id, reimbursement.tweet.get_url())
        log.info(msg.format(*args))
