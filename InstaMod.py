# coding: utf-8

# Python 2.7 imports
from itertools import product

from colorlog.escape_codes import escape_codes
from praw.exceptions import ClientException

try:
    import heapq
    from operator import itemgetter
except ImportError:
    pass

import time
from collections import Counter
from datetime import datetime

import argparse
import praw
import prawcore
from dateutil import relativedelta
from nltk.tokenize import sent_tokenize
from tinydb import Query
import colorlog

# File system imports
from sub import Subreddit

parser = argparse.ArgumentParser(description='Runs InstaMod in an infinite loop. Most configuration is controlled as described in the readme. '
                                             'See README for more information. This script should be run as a service.',
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Example: python InstaMod.py ThisSub ThatSub")
parser.add_argument('subreddits', type=str, nargs='+', help="one or more subreddits to process")
parser.add_argument('-a', '--analysis-age', type=int, default=30, help="user analysis cache time in minutes (0 will always reanalyze users)")
parser.add_argument('-p', '--post-limit', type=int, default=100, help="posts to read every scrape")
parser.add_argument('-v', '--verbose', action='store_true', default=False, help="verbose logging")
parser.add_argument('-l', '--locked-refresh', type=int, default=5, help="time in minutes to refresh locked thread list (in case a post has been unflaired)")
parser.add_argument('-s', '--staleness', type=int, default=60 * 60 * 24, help="the staleness threshold: comments or posts newer than this age will "
                                                                              "always be recalculated for karma, while older content will be treated "
                                                                              "as final")
args = parser.parse_args()

handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter('%(asctime)s %(log_color)s[%(levelname)s][%(name)s] %(message)s'))

logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel("INFO" if not args.verbose else "DEBUG")

# Start instance of Reddit
reddit = praw.Reddit('InstaMod')

# Initiate TinyDB Querry
find_stuff = Query()


# Returns Subreddit Object
def setSubs():
    sub_list = []

    for sub in args.subreddits:
        sub_list.append(Subreddit(sub))
    return sub_list


# Ensures user is accessible to the bot
def setUser(username):
    try:
        return reddit.redditor(username)
    except (prawcore.exceptions.NotFound, AttributeError):
        return None


# Ensures that a string consists of a number only
def checkIsInt(target_str):
    try:
        int(target_str)
        return True
    except ValueError:
        return False


# Main method for finding users to analyze
def scrapeSub(parent_sub, locked_threads):
    sub = parent_sub.sub_obj
    # Stores thread IDs for comments to be removed under
    users_dict = {}
    original_latest_comment_id = latest_comment_id = parent_sub.sub_status.get('latest_comment_id')
    if latest_comment_id:
        try:
            comment = reddit.comment(latest_comment_id)
            comment.refresh()
        except ClientException:
            logger.warn('latest_comment_id was probably deleted, loading max comments instead')
            original_latest_comment_id = latest_comment_id = None

    if latest_comment_id:
        logger.info('Scraping comments starting with latest comment {id}'.format(id=latest_comment_id))
    else:
        logger.info('Scraping full comment history')

    comments = sub.comments(params={'before': 't1_{}'.format(latest_comment_id)} if latest_comment_id else None)
    for comment in comments:
        if not latest_comment_id:
            latest_comment_id = comment.id
        latest_comment_id = max(latest_comment_id, comment.id)
        user = comment.author
        username = str(user)
        if username not in users_dict:
            users_dict[username] = {'reddit_user': user, 'user': parent_sub.getUserInfo(username)}

    logger.info('Scraping submissions\n')
    posts = sub.new(limit=args.post_limit)
    for post in posts:
        user = post.author
        username = str(user)
        # todo: smarter user analysis for posts since they are pretty stable
        # skip this for now
        # if username not in users_dict:
        #     users_dict[username] = {'reddit_user': user, 'user': parent_sub.getUserInfo(username)}

        # Check if post has flair for thread locking and save post ID
        if parent_sub.main_config['thread_lock']:
            if post.link_flair_text is not None:
                lock_status = checkThreadLock(parent_sub, post.link_flair_text)
                if lock_status is not None:
                    if post.fullname not in locked_threads:
                        locked_threads[post.fullname] = lock_status
                        logger.info('Post: {} was added to locked_threads: {}'.format(post.fullname, lock_status))
                        if parent_sub.threadlock_config.get('sticky_comment'):
                            # it should be the first comment if it exists
                            post.comment_limit = 1
                            try:
                                is_already_stickied = post.comments[0].stickied
                            except IndexError:
                                is_already_stickied = False
                            if not is_already_stickied:
                                logger.info('Adding sticky comment to {post}'.format(post=post.id))
                                comment = post.reply(parent_sub.threadlock_config['sticky_comment'])
                                comment.mod.distinguish(sticky=True)

    analyzeUsers(parent_sub, users_dict, locked_threads)

    # Recheck comments for users who should have comments auto deleted or for comments in locked threads
    if parent_sub.main_config['thread_lock'] is True or parent_sub.main_config['sub_lock'] is True:
        comments = sub.comments(params={'before': 't1_{}'.format(original_latest_comment_id)} if original_latest_comment_id else {})
        for comment in comments:
            user = comment.author
            username = str(user)
            submis_id = comment.link_id
            user_info = parent_sub.getUserInfo(username)

            # User discovered who has not yet been analyzed or is whitelisted
            if user_info is None:
                continue

            if comment.is_submitter:
                logger.info('Skipping removal for {username} comment in own thread {post_id}'.format(username=username, post_id=submis_id))
                continue

            if parent_sub.main_config['sub_lock']:
                # this doesn't appear to be implemented
                # user_locked = handelSubLock(parent_sub, user_info)
                user_locked = False

                if user_locked:
                    lock_type = parent_sub.sublock_config[user_locked]
                    action = lock_type['action']

                    if action == 'REMOVE':
                        message_info = parent_sub.threadlock_config['remove_message']
                        if message_info is not None:
                            post = comment.submission
                            user.message(message_info[0], ("\n\nSubreddit: " + parent_sub.sub_name + "\n\nPost: " + post.title + "\n\nLock Type: " + lock_type[
                                'lock_ID'] + "\n\nComment: " + comment.body + "\n\n" + message_info[1]))
                            logger.info('{user} notified'.format(user=user))
                        logger.info('{red}Comment by {user} removed'.format(red=escape_codes['red'], user=user))
                        comment.mod.remove()
                    elif action == 'SPAM':
                        logger.info('{red}Comment by {user} spammed'.format(red=escape_codes['red'], user=user))
                        comment.mod.remove(spam=True)

            # Check if comment is in a locked thread
            if comment.banned_by != reddit.user.me().name and submis_id in locked_threads and parent_sub.should_act_on(user):
                lock_status = locked_threads[submis_id]

                if handleThreadLock(parent_sub, lock_status, user_info):
                    lock_type = parent_sub.threadlock_config[lock_status]
                    action = lock_type['action']

                    if action == 'REMOVE':
                        message_info = parent_sub.threadlock_config['remove_message']
                        if message_info is not None:
                            post = comment.submission
                            user.message(message_info[0], ("\n\nSubreddit: " + parent_sub.sub_name + "\n\nPost: " + post.title + "\n\nLock Type: " + lock_type[
                                'flair_ID'] + "\n\nComment: " + comment.body + "\n\n" + message_info[1]))
                            logger.info('{user} notified'.format(user=user))
                        logger.info('{red}Comment by {user} removed'.format(red=escape_codes['red'], user=user))
                        comment.mod.remove()
                    elif action == 'SPAM':
                        logger.info('{red}Comment by {user} spammed'.format(red=escape_codes['red'], user=user))
                        comment.mod.remove(spam=True)
    parent_sub.sub_status['latest_comment_id'] = latest_comment_id
    parent_sub.save_sub_status()


# Analyze a user's comments and posts and extract data from them
def analyzeHistory(parent_sub, reddit_user, user):
    # Data points
    username = str(reddit_user)
    date_created = reddit_user.created
    analysis_time = datetime.utcnow()
    total_comment_karma = reddit_user.comment_karma
    total_post_karma = reddit_user.link_karma
    total_karma = total_comment_karma + total_post_karma

    counters = {
        'fresh': {
            'comment_karma_counter': Counter(),
            'post_karma_counter': Counter(),
            'pos_comment_counter': Counter(),
            'neg_comment_counter': Counter(),
            'pos_post_counter': Counter(),
            'neg_post_counter': Counter(),
            'pos_QC_counter': Counter(),
            'neg_QC_counter': Counter()
        },
        'stale': {}
    }
    fresh_counters = counters['fresh']
    stale_counters = counters['stale']

    if user:
        latest_comment_id = user.latest_comment_id
        latest_stale_comment_id = user.latest_stale_comment_id
        latest_post_id = user.latest_post_id
        latest_stale_post_id = user.latest_stale_post_id
        stale_counters['comment_karma_counter'] = user.comment_karma_counter
        stale_counters['post_karma_counter'] = user.post_karma_counter
        stale_counters['pos_comment_counter'] = user.pos_comment_counter
        stale_counters['neg_comment_counter'] = user.neg_comment_counter
        stale_counters['pos_post_counter'] = user.pos_post_counter
        stale_counters['neg_post_counter'] = user.neg_post_counter
        stale_counters['pos_QC_counter'] = user.pos_QC_counter
        stale_counters['neg_QC_counter'] = user.neg_QC_counter
    else:
        latest_comment_id = None
        latest_stale_comment_id = None
        latest_post_id = None
        latest_stale_post_id = None
        stale_counters['comment_karma_counter'] = Counter()
        stale_counters['post_karma_counter'] = Counter()
        stale_counters['pos_comment_counter'] = Counter()
        stale_counters['neg_comment_counter'] = Counter()
        stale_counters['pos_post_counter'] = Counter()
        stale_counters['neg_post_counter'] = Counter()
        stale_counters['pos_QC_counter'] = Counter()
        stale_counters['neg_QC_counter'] = Counter()

    # Parse comments
    cmnt_score = 0

    if latest_stale_comment_id:
        logger.info('\t\tAnalyzing user {username} comments starting with latest stale comment {id}'.format(username=username, id=latest_stale_comment_id))
    else:
        logger.info('\t\tAnalyzing user {username} full comment history (1000 limit)'.format(username=username))

    count = 0
    for comment in reddit_user.comments.new(limit=None, params={'before': 't1_{}'.format(latest_stale_comment_id)} if latest_stale_comment_id else {}):
        count += 1
        is_stale_comment = comment.created_utc < (time.time() - args.staleness)
        counters_to_use = stale_counters if is_stale_comment else fresh_counters
        if not latest_comment_id:
            latest_comment_id = comment.id
        if is_stale_comment:
            if not latest_stale_comment_id:
                latest_stale_comment_id = comment.id
            latest_stale_comment_id = max(latest_stale_comment_id, comment.id)
        latest_comment_id = max(latest_comment_id, comment.id)
        cmnt_sub = comment.subreddit
        sub_name = str(cmnt_sub)
        cmnt_score = comment.score
        word_count = countWords(comment.body)
        abbrev = None

        if sub_name.upper() in parent_sub.all_subs:
            abbrev = parent_sub.all_subs[sub_name.upper()]

        if abbrev is not None:
            counters_to_use['comment_karma_counter'][abbrev] += cmnt_score
            if cmnt_score > 0:
                counters_to_use['pos_comment_counter'][abbrev] += 1
            elif cmnt_score < 0:
                counters_to_use['neg_comment_counter'][abbrev] += 1

            if cmnt_score >= parent_sub.QC_config['pos_karma']:
                if parent_sub.QC_config['pos_words'] is None:
                    counters_to_use['pos_QC_counter'][abbrev] += 1
                elif word_count >= parent_sub.QC_config['pos_words']:
                    counters_to_use['pos_QC_counter'][abbrev] += 1
            if cmnt_score <= parent_sub.QC_config['neg_karma']:
                if parent_sub.QC_config['neg_words'] is None:
                    counters_to_use['neg_QC_counter'][abbrev] += 1
                elif word_count <= parent_sub.QC_config['neg_words']:
                    counters_to_use['neg_QC_counter'][abbrev] += 1
    logger.info('\t\tScraped {count} comments for {user}'.format(count=count, user=username))

    # Parse posts
    if latest_stale_post_id:
        logger.info('\t\tAnalyzing user {username} posts starting with latest stale post {id}'.format(username=username, id=latest_stale_post_id))
    else:
        logger.info('\t\tAnalyzing user {username} full post history'.format(username=username))

    count = 0
    workaround_post_id = latest_stale_post_id
    for post in reddit_user.submissions.new(limit=None, params={'before': 't3_'.format(latest_stale_post_id)} if latest_stale_post_id else {}):
        # submission listing API doesn't seem to honor before param
        if workaround_post_id and post.id <= workaround_post_id:
            break
        count += 1
        is_stale_post = post.created_utc < (time.time() - args.staleness)
        counters_to_use = stale_counters if is_stale_post else fresh_counters
        if is_stale_post:
            if not latest_stale_post_id:
                latest_stale_post_id = post.id
            latest_stale_post_id = max(latest_stale_post_id, post.id)
        post_sub = post.subreddit
        sub_name = str(post_sub)
        post_score = post.score
        abbrev = None
        if not latest_post_id:
            latest_post_id = post.id
        latest_post_id = max(latest_post_id, post.id)

        if sub_name in parent_sub.A_subs:
            abbrev = parent_sub.A_subs[sub_name.upper()]
        elif sub_name in parent_sub.B_subs:
            abbrev = parent_sub.B_subs[sub_name.upper()]

        if abbrev is not None:
            counters_to_use['post_karma_counter'][abbrev] += cmnt_score

            if post_score > 0:
                counters_to_use['pos_comment_counter'][abbrev] += 1
            elif post_score < 0:
                counters_to_use['neg_comment_counter'][abbrev] += 1
    logger.info('\t\tScraped {count} posts for {user}'.format(count=count, user=username))
    # storing all stale data
    user = parent_sub.makeUser(reddit_user, username, date_created, analysis_time, latest_comment_id, latest_post_id, latest_stale_comment_id,
                               latest_stale_post_id, total_comment_karma, total_post_karma,
                               total_karma, stale_counters['comment_karma_counter'], stale_counters['post_karma_counter'],
                               stale_counters['pos_comment_counter'], stale_counters['neg_comment_counter'], stale_counters['pos_post_counter'],
                               stale_counters['neg_post_counter'], stale_counters['pos_QC_counter'], stale_counters['neg_QC_counter'])

    stale_net_QC = user.get_info_dict()['net QC']
    stale_pos_QC = user.get_info_dict()['positive QC']
    stale_neg_QC = user.get_info_dict()['negative QC']

    # add fresh data to persisted stale data
    for counter_name, counter in fresh_counters.items():
        stale_count = user.__getattribute__(counter_name)
        user.__setattr__(counter_name, stale_count + counter)

    fresh_net_QC = user.get_info_dict()['net QC']
    fresh_pos_QC = user.get_info_dict()['positive QC']
    fresh_neg_QC = user.get_info_dict()['negative QC']
    sub = parent_sub.sub_abbrev
    logger.info('\t\t{}: stale QC {}-{}={} fresh QC: {}-{}={}'.format(username, stale_pos_QC[sub], stale_neg_QC[sub], stale_net_QC[sub],
                                                                      fresh_pos_QC[sub], fresh_neg_QC[sub], fresh_net_QC[sub]))
    return user


# Get users' history and process data based on info
def analyzeUsers(parent_sub, users_dict, locked_threads):
    logger.info('Analyzing all users in current list: ' + str(len(users_dict)) + '\n')
    parent_sub_id = parent_sub.sub_obj.fullname

    for count, (username, user_dict) in enumerate(sorted(users_dict.items())):
        reddit_user = user_dict['reddit_user']
        user = user_dict['user']
        if count in map(lambda t: int(1.0 * t[0] / 20 * t[1]), product(range(20), [len(users_dict)])):
            logger.info('{:.0%} done'.format(1.0 * count / len(users_dict)))
        user_analysis_age = parent_sub.get_user_analysis_age(username)
        skip_analysis = True if user_analysis_age and user_analysis_age < args.analysis_age * 60 else False
        if skip_analysis:
            logger.info('Skipping {username} due to recent analysis {age} seconds'.format(username=username, age=user_analysis_age))
            continue
        try:
            logger.info('\t{}'.format(username))
            if not parent_sub.should_act_on(reddit_user):
                logger.info('Skipping analysis on white/grey/mod user {user}'.format(user=username))
                continue
            user_info = analyzeHistory(parent_sub, reddit_user, user)
        except Exception:
            logger.exception('Exception processing user {}'.format(username))
            continue
        if user_info.latest_stale_comment_id:
            logger.info('\t\tCheck user {user} for removals based on fresh data starting with {id}'.format(user=username, id=user_info.latest_stale_comment_id))
            params = {'before': 't1_{}'.format(user_info.latest_stale_comment_id)} if user_info.latest_stale_comment_id else {}
        else:
            logger.info('\t\tCheck user {user} for removals based on fresh data'.format(user=username))
            params = {}
        count = 0
        # process any pending removals based on fresh data
        for comment in reddit_user.comments.new(params=params):
            if comment.subreddit_id != parent_sub_id:
                continue
            count += 1
            submis_id = comment.link_id

            if comment.is_submitter:
                logger.info('Skipping removal for {username} comment in own thread {post_id}'.format(username=username, post_id=submis_id))
                continue

            # todo: this is all copy/pasted
            # Check if comment is in a locked thread
            if comment.banned_by != reddit.user.me().name and submis_id in locked_threads and parent_sub.should_act_on(user):
                logger.debug('Fresh comment by {username} in locked thread'.format(username=username))
                lock_status = locked_threads[submis_id]
                if handleThreadLock(parent_sub, lock_status, user_info):
                    lock_type = parent_sub.threadlock_config[lock_status]
                    action = lock_type['action']

                    if action == 'REMOVE':
                        message_info = parent_sub.threadlock_config['remove_message']
                        if message_info is not None:
                            post = comment.submission
                            user.message(message_info[0], ("\n\nSubreddit: " + parent_sub.sub_name + "\n\nPost: " + post.title + "\n\nLock Type: " + lock_type[
                                'flair_ID'] + "\n\nComment: " + comment.body + "\n\n" + message_info[1]))
                            logger.info('\t\t{user} notified'.format(user=username))
                        logger.info('\t\t{red}Comment by {user} removed'.format(red=escape_codes['red'], user=username))
                        comment.mod.remove()
                    elif action == 'SPAM':
                        logger.info('\t\t{red}Comment by {user} spammed'.format(red=escape_codes['red'], user=username))
                        comment.mod.remove(spam=True)
        logger.info('\t\tRechecked {count} comments'.format(count=count))

        # Subreddit Progression
        if parent_sub.main_config['sub_progression']:
            # Check info against each tier's rule
            for tier, config in parent_sub.progression_config.items():
                if tier.startswith('tier') and checkInfoTag(parent_sub, user_info, config):
                    flair_text = config['flair_text']
                    flair_css = config['flair_css']
                    permissions = config['permissions']

                    parent_sub.appendFlair(reddit_user, flair_text, flair_css)
                    if permissions == 'CUSTOM_FLAIR':
                        parent_sub.addWhitelist(username)
                    elif permissions == 'FLAIR_ICONS':
                        parent_sub.addImgFlair(username)
                    # Break on the first tier matched to avoid multiple tiers
                    break

        # Subreddit Tags
        if parent_sub.main_config['sub_tags']:
            # Check info against each tag's rule
            for tag, config in parent_sub.subtag_config.items():
                if tag.startswith('subtag'):
                    hold_subs = getSubTag(parent_sub, user_info, config)
                    pre_text = config['pre_text']
                    post_text = config['post_text']

                    for sub in hold_subs:
                        parent_sub.appendFlair(reddit_user, (pre_text + sub + post_text), None)

        # Account Age Tag
        if parent_sub.main_config['accnt_age']:
            userCreated = user_info.date_created
            tdelta = relativedelta.relativedelta(datetime.utcnow(), datetime.utcfromtimestamp(user_info.date_created))
            if tdelta.months <= parent_sub.main_config['accnt_age']:
                # create flair with appropriate time breakdown
                if tdelta.years < 1:
                    if tdelta.months < 1:
                        days = tdelta.days
                        flairText = str(days)
                        if days == 1:
                            parent_sub.appendFlair(username, flairText + ' day old', None)
                        else:
                            parent_sub.appendFlair(username, flairText + ' days old', None)
                    else:
                        months = tdelta.months
                        flairText = str(months)
                        if months == 1:
                            parent_sub.appendFlair(reddit_user, flairText + ' month old', None)
                        else:
                            parent_sub.appendFlair(reddit_user, flairText + ' months old', None)
        # if parent_sub.main_config['ratelimit'] == True:
        # 	if parent_sub.ratelimit_config['COMMENTS']['metric'] != None:
        # 		config = parent_sub.ratelimit_config['COMMENTS']
        # 		if checkInfoTag(parent_sub, user_info, config):
        # 			comment_hist = user_info.comment_rate
        # 			max = config['max']
        # 			while len(comment_hist) > max:
        # 				comment = reddit.comment(id=comment_hist.pop[0])
        # 				author = comment.author
        # 				username = str(author)
        # 				post = comment.submission
        #
        # 				message_info = config['comment_remove_message']
        # 				author.message(message_info[0], ("\n\nSubreddit: " + parent_sub.sub_name + "\n\nPost: " + post.title + "\n\nComment Rate Limit: Over " + str(max) + ' comments in under ' + str(config['interval']) + ' hours' + "\n\nComment: " + comment.body + "\n\n" + message_info[1]))
        # 				comment.mod.remove()
        # 	if parent_sub.ratelimit_config['SUBMISSIONS']['metric'] != None:
        # 		config = parent_sub.ratelimit_config['SUBMISSIONS']
        # 		if checkInfoTag(parent_sub, user_info, config):
        # 			post_hist = user_info.post_rate
        # 			max = config['max']
        # 			while len(post_hist) > max:
        # 				post = reddit.submission(id=post_hist.pop[0])
        # 				author = comment.author
        # 				username = str(author)
        #
        # 				message_info = config['comment_remove_message']
        # 				author.message(message_info[0], ("\n\nSubreddit: " + parent_sub.sub_name + "\n\nPost: " + post.title + "\n\nComment Rate Limit: Over " + str(max) + ' comments in under ' + str(config['interval']) + ' hours' + "\n\n" + message_info[1]))
        # 				comment.mod.remove()

    # Assign users' flair based on analysis
    parent_sub.flairUsers()


# Check for PMs that require automated actions
def readPMs(parent_sub):
    messages = reddit.inbox.unread()
    for message in messages:
        author = message.author
        username = str(author)
        # Command messages must have '!' in the start of their subject
        if message.subject.startswith('!' + parent_sub.sub_name) and username in parent_sub.mods:
            logger.info('Message accepted: ' + message.body)
            message_words = message.body.split()

            if len(message_words) != 2:
                message.reply(
                    'More or less than 2 arguments were found in the body of the message. Please try again with the proper syntax. If you believe this is an error, please contact /u/shimmyjimmy97')
                message.mark_read()
                logger.warn('Message resolved without action: Invalid number of arguments')
                continue

            # Target username must be the second word listed
            else:
                target_username = message_words[1]
                user = setUser(target_username)
                if user is None:
                    message.reply(
                        "The user was not able to be accessed by InstaMod. This could be becasue they don't exist, are shadowbanned, or a server error. If you feel that this is a mistake, please contact /u/shimmyjimmy97.")
                    message.mark_read()
                    logger.warn('Message resolved without action: Target user not accessible')
                    continue
                # Whitelist
                if message_words[0] == "!whitelist":
                    if str(user) not in parent_sub.whitelist:
                        parent_sub.addWhitelist(target_username)
                        message.reply(
                            'The user: ' + target_username + ' has been added to the whitelist and will no longer recieve new flair. They are also now eligible for custom flair. The user will be notified of their whitelisted status now.')
                        message.mark_read()
                        user.message(
                            'You have been granted permission to assign custom flair! A moderator of r/' + parent_sub.sub_name + ' has granted your account permission to assign custom flair. To choose your flair, send me (/u/InstaMod) a private message with the syntax:\n\nSubject:\n\n    !SubredditName\n\nBody:    !flair flair text here\n\nFor example, if you want your flair to say "Future Proves Past" then your PM should look like this:\n\n    !flair Future Proves Past\n\n If you have any questions, please send /u/shimmyjimmy97 a PM, or contact the moderators.')
                        logger.info('Message resolved successfully')
                    else:
                        message.reply('The user: ' + target_username + ' is already in the whitelist')
                        message.mark_read()
                        logger.info('Message resolved without action: User already in whitelist')
                # Graylist/Greylist
                if message_words[0] == "!greylist" or message_words[0] == '!graylist':
                    if str(user) not in parent_sub.graylist:
                        parent_sub.addGraylist(target_username)
                        message.reply('The user: ' + target_username + ' has been added to the graylist and will no longer recieve new flair.')
                        message.mark_read()
                        logger.info('Message resolved successfully')
                    else:
                        message.reply('The user: ' + target_username + ' is already in the graylist')
                        message.mark_read()
                        logger.info('Message resolved without action: User already in graylist')
                # Custom Flair
                if message_words[0] == '!flair':
                    if target_username in parent_sub.whitelist or username in parent_sub.mods:
                        new_flair = message.body[7:]
                        parent_sub.flairUser(user, new_flair)
                        message.reply('Your flair has been set! It should now read:\n\n' + new_flair)
                        message.mark_read()
                        logger.info('Message resolved successfully')
                    else:
                        message.reply(
                            'You are not on the list of approved users for custom flair. If you feel that this is a mistake, please contact /u/shimmyjimmy97 or message the moderators.')
                        message.mark_read()
                        logger.info('Message resolved without action: User not approved for custom flair')
                        continue


# Compares link flair to sub lock config flairs	
def checkThreadLock(parent_sub, link_flair):
    for lock in parent_sub.threadlock_config:
        if lock.startswith('threadlock') and link_flair == parent_sub.threadlock_config[lock]['flair_ID']:
            return lock
    return None


# Creates a list of target subreddits from the config file settings
def getTargetSubs(parent_sub, target_subs):
    sub_list = []
    if target_subs == 'A_SUBS':
        for sub in parent_sub.A_subs:
            sub_list.append(parent_sub.A_subs[sub])
    elif target_subs == 'B_SUBS':
        for sub in parent_sub.B_subs:
            sub_list.append(parent_sub.B_subs[sub])
    elif target_subs == 'ALL_SUBS':
        for sub in parent_sub.all_subs:
            sub_list.append(parent_sub.all_subs[sub])
    else:
        for abbrev in target_subs:
            if abbrev is not None:
                sub_list.append(abbrev)
    return sub_list


# Makes a comparison based on config rule settings
def checkComparison(comparison, total_value, value):
    if comparison == 'LESS_THAN':
        if total_value < value:
            return True
        return False
    elif comparison == 'GREATER_THAN':
        if total_value > value:
            return True
        return False
    elif comparison == 'EQUAL_TO':
        if total_value == value:
            return True
        return False
    elif comparison == 'NOT_EQUAL_TO':
        if total_value != value:
            return True
        return False
    elif comparison == 'GREATER_THAN_EQUAL_TO':
        if total_value >= value:
            return True
        return False
    elif comparison == 'LESS_THAN_EQUAL_TO':
        if total_value <= value:
            return True
        return False
    else:
        return False


# Sort a Counter object from least common to most common
def getLeastCommon(array, to_find=None):
    counter = Counter(array)
    if to_find is None:
        return sorted(counter.items(), key=itemgetter(1), reverse=False)
    return heapq.nsmallest(to_find, counter.items(), key=itemgetter(1))


# Check comments in locked thread against the threads rule
def handleThreadLock(parent_sub, lock_status, user_info):
    lock_type = parent_sub.threadlock_config[lock_status]
    metric = lock_type['metric']
    target_subs = lock_type['target_subs']
    comparison = lock_type['comparison']
    value = lock_type['value']

    user_data = user_info.get_info_dict()[metric]
    sub_list = getTargetSubs(parent_sub, target_subs)
    total_value = 0
    if 'total' in metric:
        total_value = user_data
    else:
        for abbrev in sub_list:
            total_value += user_data.get(abbrev, 0)
    logger.debug('Lock check {user} {comparison} {total_value} {value}'.format(user=user_info.username, comparison=comparison, total_value=total_value,
                                                                               value=value))
    return checkComparison(comparison, total_value, value)


# Make Subreddit Tags based on users history			
def getSubTag(parent_sub, user_info, config):
    metric = config['metric']
    target_subs = config['target_subs']
    sort = config['sort']
    tag_cap = config['tag_cap']
    comparison = config['comparison']
    value = config['value']

    # Makes a list of subs to total data from
    sub_list = getTargetSubs(parent_sub, target_subs)
    user_data = user_info.get_info_dict()[metric]
    hold_subs = []

    if sort == 'MOST_COMMON':
        tag_count = 0
        for sub in user_data.most_common(5):
            if tag_count >= tag_cap:
                break
            abbrev = sub[0]
            data = sub[1]
            if abbrev in sub_list:
                if checkComparison(comparison, data, value):
                    hold_subs.append(abbrev)
                    tag_count += 1
            else:
                logger.info('Sub not in sub list')
        return hold_subs
    if sort == 'LEAST_COMMON':
        tag_count = 0
        sorted_data = user_data.most_common()[:-tag_cap - 1:-1]
        for sub in sorted_data:
            if tag_count >= tag_cap:
                break
            abbrev = sub[0]
            data = sub[1]
            if abbrev in sub_list:
                if checkComparison(comparison, data, value):
                    logger.info('Sub accepted')
                    hold_subs.append(sub[0])
                    tag_count += 1
            else:
                logger.info('Sub not in list')
        return hold_subs


# Check user info agaisnt sub rule					
def checkInfoTag(parent_sub, user_info, config):
    metric = config['metric']
    if metric == 'ELSE':
        return True
    target_subs = config['target_subs']
    comparison = config['comparison']
    value = config['value']

    # Makes a list of subs to total data from
    sub_list = getTargetSubs(parent_sub, target_subs)

    user_data = user_info.get_info_dict()[metric]
    total_value = 0
    if 'total' in metric:
        total_value = user_data
    else:
        for abbrev in sub_list:
            total_value += user_data[abbrev]

    return checkComparison(comparison, total_value, value)


# Count the number of words in a comment
def countWords(text):
    word_count = 0
    sentences = sent_tokenize(text)

    for sentence in sentences:
        words = sentence.split(' ')
        for word in words:
            if word.isalpha():
                word_count += 1

    return word_count


if __name__ == '__main__':
    locked_threads = {}
    time_to_refresh_locked_threads = time.time()
    while True:
        start_time = time.time()
        try:
            sub_list = setSubs()
            for subreddit in sub_list:
                if subreddit.should_act_on(reddit.user.me().name):
                    raise Exception('The bot account needs to be in mod list or white list.')
                # clear the locked_threads every 5 minutes so we pick up unflaired posts
                if time.time() >= time_to_refresh_locked_threads:
                    locked_threads[subreddit.sub_name] = {}
                    time_to_refresh_locked_threads = time.time() + 60 * 5
                logger.info('Scraping subreddit: ' + subreddit.sub_name)
                if subreddit.main_config.get('read_pms'):
                    readPMs(subreddit)
                scrapeSub(subreddit, locked_threads[subreddit.sub_name])
                logger.info('Finished subreddit: ' + subreddit.sub_name)
            time_diff = int(time.time() - start_time)
        except Exception:
            logger.exception('Exception in main loop')
            time_diff = 0
        time_to_sleep = 60 - time_diff
        if time_to_sleep > 0:
            logger.info('Sleeping {} seconds'.format(time_to_sleep))
            time.sleep(time_to_sleep)
