from copy import copy, deepcopy

import praw
import prawcore
from six import string_types
import json
from collections import Counter
from datetime import datetime, date
from dateutil import relativedelta
import dateutil.parser
from tinydb import TinyDB, Query
import logging

logger = logging.getLogger(__name__)

# start instance of Reddit
reddit = praw.Reddit('InstaMod')

# initialize sub specific global variables
find_stuff = Query()


# convert datetime so databse can read it
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


def setUser(username):
    try:
        return reddit.redditor(username)
    except (prawcore.exceptions.NotFound, AttributeError):
        return None


class User(object):
    def __init__(user_info, parent_sub, username, date_created, analysis_time, latest_comment_id, latest_post_id, latest_stale_comment_id, latest_stale_post_id,
                 total_comment_karma, total_post_karma, total_karma, comment_karma_counter, post_karma_counter, pos_comment_counter, neg_comment_counter,
                 pos_post_counter, neg_post_counter, pos_QC_counter, neg_QC_counter):
        user_info.parent_sub = parent_sub
        user_info.username = username
        user_info.date_created = date_created
        user_info.analysis_time = analysis_time
        user_info.latest_comment_id = latest_comment_id
        user_info.latest_stale_comment_id = latest_stale_comment_id
        user_info.latest_post_id = latest_post_id
        user_info.latest_stale_post_id = latest_stale_post_id
        user_info.total_comment_karma = total_comment_karma
        user_info.total_post_karma = total_post_karma
        user_info.total_karma = total_karma

        user_info.comment_karma_counter = comment_karma_counter

        user_info.post_karma_counter = post_karma_counter

        user_info.pos_comment_counter = pos_comment_counter

        user_info.neg_comment_counter = neg_comment_counter

        user_info.pos_post_counter = pos_post_counter

        user_info.neg_post_counter = neg_post_counter

        user_info.pos_QC_counter = pos_QC_counter

        user_info.neg_QC_counter = neg_QC_counter

        userDB = TinyDB(parent_sub.sub_name + '/userInfo.json')
        comment_karma_str = ''
        for sub in comment_karma_counter:
            comment_karma_str += (sub + ' ' + str(comment_karma_counter[sub]) + ' ')

        post_karma_str = ''
        for sub in post_karma_counter:
            post_karma_str += (sub + ' ' + str(post_karma_counter[sub]) + ' ')

        pos_comment_str = ''
        for sub in pos_comment_counter:
            pos_comment_str += (sub + ' ' + str(pos_comment_counter[sub]) + ' ')

        neg_comment_str = ''
        for sub in neg_comment_counter:
            neg_comment_str += (sub + ' ' + str(neg_comment_counter[sub]) + ' ')

        pos_post_str = ''
        for sub in pos_post_counter:
            pos_post_str += (sub + ' ' + str(pos_post_counter[sub]) + ' ')

        neg_post_str = ''
        for sub in neg_post_counter:
            neg_post_str += (sub + ' ' + str(neg_post_counter[sub]) + ' ')

        pos_QC_str = ''
        for sub in pos_QC_counter:
            pos_QC_str += (sub + ' ' + str(pos_QC_counter[sub]) + ' ')

        neg_QC_str = ''
        for sub in neg_QC_counter:
            neg_QC_str += (sub + ' ' + str(neg_QC_counter[sub]) + ' ')

        net_QC_str = ''
        net_QC = deepcopy(pos_QC_counter)
        for sub in net_QC:
            net_QC_str += (sub + ' ' + str(net_QC[sub] - neg_QC_counter[sub]) + ' ')

        # str_created = json_serial(date_created)
        if not isinstance(analysis_time, string_types):
            str_analyzed = json_serial(analysis_time)
        else:
            str_analyzed = analysis_time
        doc = {'username': username, 'date_created': date_created, 'analysis_time': str_analyzed, 'latest_comment_id': latest_comment_id,
               'latest_stale_comment_id': latest_stale_comment_id,  'latest_post_id': latest_post_id, 'latest_stale_post_id': latest_stale_post_id,
               'total_comment_karma': total_comment_karma, 'total_post_karma': total_post_karma, 'total_karma': total_karma,
               'comment_karma_counter': comment_karma_str, 'post_karma_counter': post_karma_str, 'pos_comment_counter': pos_comment_str,
               'neg_comment_counter': neg_comment_str, 'pos_post_counter': pos_post_str, 'neg_post_counter': neg_post_str, 'pos_QC_counter': pos_QC_str,
               'neg_QC_counter': neg_QC_str, 'net_QC_counter': net_QC_str}
        # user_search = userDB.search(find_stuff.username == username)
        # if user_search:
        #     logger.info('Updating existing ')
        #     userDB.update(doc, doc_ids=[user_search.doc_id])
        # else:
        # existing = userDB.search(find_stuff.username == username)
        userDB.upsert(doc, Query().username == username)

    def get_info_dict(self):
        net_QC = deepcopy(self.pos_QC_counter)
        for sub in net_QC:
            net_QC[sub] -= self.neg_QC_counter[sub]
        return {
            'parent_sub': self.parent_sub,
            'username': self.username,
            'date created': self.date_created,
            'analysis time': self.analysis_time,
            'latest comment id': self.latest_comment_id,
            'latest stale comment id': self.latest_stale_comment_id,
            'latest post id': self.latest_post_id,
            'latest stale post id': self.latest_stale_post_id,
            'comment karma': self.comment_karma_counter,
            'post karma': self.post_karma_counter,
            'total comment karma': self.total_comment_karma,
            'total post karma': self.total_post_karma,
            'total karma': self.total_karma,
            'positive comments': self.pos_comment_counter,
            'negative comments': self.neg_comment_counter,
            'positive posts': self.pos_post_counter,
            'negative posts': self.neg_post_counter,
            'positive QC': self.pos_QC_counter,
            'negative QC': self.neg_QC_counter,
            'net QC': net_QC
        }
