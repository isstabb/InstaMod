import time
from collections import Counter
from datetime import datetime
from unittest import TestCase
try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from InstaMod import handleThreadLock
from sub import Subreddit
from user import User


class TestInstaMod(TestCase):
    testsub_config = \
"""{
    'SUB_CONFIG' : {
        'name' : 'testsub',
        'abbrev' : 'test',
        'mods' : ('mod1', 'mod2'),
        'thread_lock' : True,
        'sub_lock' : False,
        'sub_progression' : False,
        'etc_tags' : False,
        'sub_tags' : False,
        'tag_expiration' : 7,
        'accnt_age' : False,
        'update_interval' : 250,
        'approved_icons' : ()
    },

    'QC_CONFIG' : {
        # Comments with values >= both of these numbers count as 1 positive QC
        'pos_karma' : 3,
        'pos_words' : None,
        # Comments with values <= both of these numbers count as 1 negative QC
        'neg_karma' : -1,
        'neg_words' : None
        # Currently only word options have the ability to be toggled off with a None value
    },

    'PROGRESS_CONFIG' : {

        # 'tier1' : {'metric' : 'positive comments',
        #            'target_subs' : ('A_SUBS'),
        #            'comparison' : 'LESS_THAN_EQUAL_TO',
        #            'value' : 10,
        #            'flair_text' : None,
        #            'flair_css' : 'new',
        #            'permissions' : None}

    },

    # Subreddit Activity Tags
    # Unique characteristics:
    # Custom flair text is replaced with 'pre_text' and 'post_text' which go before and after each subreddits abbreviations. To disable these, use an empty string '' and not None
    # Results can be soted in order from highest to lowest (MOST_COMMON) or lowest to highest (LEAST_COMMON)
    # The number of subreddits listed can be capped using the tag_cap setting
    'SUBTAG_CONFIG' : {
        # 'subtag1' : {'metric' : 'net QC',
        #              'target_subs' : ('A_SUBS'),
        #              'sort' : 'MOST_COMMON',
        #              'tag_cap' : 3,
        #              'comparison' : 'GREATER_THAN_EQUAL_TO',
        #              'value' : 15,
        #              'pre_text' : 'r/',
        #              'post_text' : ''},
        #
        # 'subtag2' : {'metric' : 'net QC',
        #              'target_subs' : ('A_SUBS'),
        #              'sort' : 'LEAST_COMMON',
        #              'tag_cap' : 3,
        #              'comparison' : 'LESS_THAN_EQUAL_TO',
        #              'value' : -1,
        #              'pre_text' : 'Trolls r/',
        #              'post_text' : ''}
    },


    # Advanced Thread Locking
    # Unique characteristics:
    # Looks for posts that have a flair matching with a rule's flair_ID, and applies the rule to all comments under the post
    # Each rule has a corresponding action, which determines how commentors that violate the rule are dealth with
    # REMOVE - remove the comment and PM the user with remove_message
    # SPAM - mark the comment as spam and do not notify the user
    'THREADLOCK_CONFIG' : {
        'threadlock1' : {'metric' : 'net QC',
                         'target_subs' : 'A_SUBS',
                         'comparison' : 'LESS_THAN_EQUAL_TO',
                         'value' : 10,
                         'flair_ID' : 'Politics',
                         'action' : 'REMOVE'},
        'remove_message': None

        # 'threadlock2' : {'metric' : 'positive comments',
        #                  'target_subs' : ('TR'),
        #                  'comparison' : 'LESS_THAN_EQUAL_TO',
        #                  'value' : 50,
        #                  'flair_ID' : 'lvl 2 Lock',
        #                  'action' : 'REMOVE'},
        #
        # 'threadlock3' : {'metric' : 'positive comments',
        #                  'target_subs' : ('TR'),
        #                  'comparison' : 'LESS_THAN_EQUAL_TO',
        #                  'value' : 100,
        #                  'flair_ID' : 'lvl 3 Lock',
        #                  'action' : 'REMOVE'},
        #
        # 'remove_message' : ('Automatic comment removal notice', 'Your account is not approved to post in this locked thread. If you have any questions, comments, or concerns, please message the moderators. This is an automated message.')
    },

    # Subreddit Locking
    # Unique characteristics:
    # This set of rules are applied to all comments on the subreddit. A SubLock can be activated and deactivated by PMing the bot
    'SUBLOCK_CONFIG' : {
        # 'sublock1' : {'metric' : 'parent_QC',
        #               'comparison' : 'LESS_THAN_EQUAL_TO',
        #               'value' : 20,
        #               'lock_ID' : 'SUBLOCK 1',
        #               'action' : 'SPAM'},
        #
        # 'remove_message' : None
    },

    # List of subreddits with a corresponding abbreviation. Subreddits with the same abbreviation will have their data points combined/totaled
    'A_SUBS' : {
        'TESTSUB' : 'test'
    },

    # Another list of subreddits
    'B_SUBS' : {
    }
}"""

    @patch('sub.praw')
    def test_handleThreadLock(self, mock_praw):
        parent_sub = Subreddit('testsub', str_config=self.testsub_config)
        empty_counter_user = User(parent_sub, 'emptyuser', time.time(), datetime.utcnow(), '', '', '', '', 1000, 2000, 3000,
                                  Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter())
        self.assertFalse(handleThreadLock(parent_sub, 'threadlock1', empty_counter_user))

        comment_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        post_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_post_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_post_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter['test'] += 11
        passing_user = User(parent_sub, 'emptyuser', time.time(), datetime.utcnow(), '', '', '', '', 1000, 2000, 3000,
                            comment_karma_counter=comment_karma_counter,
                            post_karma_counter=post_karma_counter,
                            pos_comment_counter=pos_comment_counter,
                            neg_comment_counter=neg_comment_counter,
                            pos_post_counter=pos_post_counter,
                            neg_post_counter=neg_post_counter,
                            pos_QC_counter=pos_QC_counter,
                            neg_QC_counter=neg_QC_counter)
        self.assertFalse(handleThreadLock(parent_sub, 'threadlock1', passing_user))

        comment_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        post_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_post_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_post_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter['test'] += 10
        failing_user = User(parent_sub, 'emptyuser', time.time(), datetime.utcnow(), '', '', '', '', 1000, 2000, 3000,
                            comment_karma_counter=comment_karma_counter,
                            post_karma_counter=post_karma_counter,
                            pos_comment_counter=pos_comment_counter,
                            neg_comment_counter=neg_comment_counter,
                            pos_post_counter=pos_post_counter,
                            neg_post_counter=neg_post_counter,
                            pos_QC_counter=pos_QC_counter,
                            neg_QC_counter=neg_QC_counter)
        self.assertTrue(handleThreadLock(parent_sub, 'threadlock1', failing_user))

        comment_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        post_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_post_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_post_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter['test'] += 11
        neg_QC_counter['test'] += 1
        failing_user = User(parent_sub, 'emptyuser', time.time(), datetime.utcnow(), '', '', '', '', 1000, 2000, 3000,
                            comment_karma_counter=comment_karma_counter,
                            post_karma_counter=post_karma_counter,
                            pos_comment_counter=pos_comment_counter,
                            neg_comment_counter=neg_comment_counter,
                            pos_post_counter=pos_post_counter,
                            neg_post_counter=neg_post_counter,
                            pos_QC_counter=pos_QC_counter,
                            neg_QC_counter=neg_QC_counter)
        self.assertTrue(handleThreadLock(parent_sub, 'threadlock1', failing_user))

        comment_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        post_karma_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_comment_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_post_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_post_counter = Counter({parent_sub.sub_abbrev: 0})
        pos_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        neg_QC_counter = Counter({parent_sub.sub_abbrev: 0})
        failing_user = User(parent_sub, 'emptyuser', time.time(), datetime.utcnow(), '', '', '', '', 1000, 2000, 3000,
                            comment_karma_counter=comment_karma_counter,
                            post_karma_counter=post_karma_counter,
                            pos_comment_counter=pos_comment_counter,
                            neg_comment_counter=neg_comment_counter,
                            pos_post_counter=pos_post_counter,
                            neg_post_counter=neg_post_counter,
                            pos_QC_counter=pos_QC_counter,
                            neg_QC_counter=neg_QC_counter)
        self.assertTrue(handleThreadLock(parent_sub, 'threadlock1', failing_user))
