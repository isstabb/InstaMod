import praw
import prawcore
import json
from datetime import datetime, date
from dateutil import relativedelta
import dateutil.parser
from tinydb import TinyDB, Query, where
from collections import Counter
from user import User
from ast import literal_eval
import logging

logger = logging.getLogger(__name__)

# start instance of Reddit
reddit = praw.Reddit('InstaMod')

# initialize sub specific global variables
find_stuff = Query()


def setUser(username):
    try:
        return reddit.redditor(username)
    except (prawcore.exceptions.NotFound, AttributeError):
        return None


def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


# Subreddit objectclass Subreddit:
class Subreddit:
    def __init__(sub, sub_name, str_config=None):
        # save current time
        current_time = datetime.utcnow()

        if not str_config:
            str_config = reddit.subreddit(sub_name).wiki['InstaModSettings'].content_md
        sub_config = literal_eval(str_config)

        sub.main_config = sub_config['SUB_CONFIG']
        sub.QC_config = sub_config['QC_CONFIG']
        sub.progression_config = sub_config['PROGRESS_CONFIG']
        sub.subtag_config = sub_config['SUBTAG_CONFIG']
        sub.threadlock_config = sub_config['THREADLOCK_CONFIG']
        sub.sublock_config = sub_config['SUBLOCK_CONFIG']

        sub.A_subs = sub_config['A_SUBS']
        sub.B_subs = sub_config['B_SUBS']
        sub.all_subs = sub_config['B_SUBS']
        sub.all_subs.update(sub.A_subs)

        sub.whitelist = []
        sub.graylist = []
        sub.current_users = []
        sub.expired_users = []
        sub.users_and_flair = {}
        sub.flair_img = []
        sub.lock_mode = None

        sub.mods = sub.main_config['mods']
        sub.sub_name = sub_name
        sub.sub_abbrev = sub_config['SUB_CONFIG']['abbrev']
        sub.sub_obj = reddit.subreddit(sub_name)

        try:
            with open(sub_name + '/sub_status.json') as fp:
                sub.sub_status = json.load(fp)
        except Exception:
            sub.sub_status = {}

        whitelistDB = TinyDB(sub_name + '/whitelist.json')
        for username in whitelistDB:
            user = setUser(username['username'])
            if user is not None:
                sub.whitelist.append(user)
        logger.info('All users read from whitelist\n')

        graylistDB = TinyDB(sub_name + '/graylist.json')
        for username in graylistDB:
            user = setUser(username['username'])
            if user is not None:
                sub.graylist.append(user)
        logger.info('All users read from greylist\n')

        currentDB = TinyDB(sub_name + '/userInfo.json')
        for user_info in currentDB:
            tdelta = current_time - dateutil.parser.parse(user_info['analysis_time'])
            exp_length = sub.main_config['tag_expiration']
            # remove users with expired flair and add current users to list
            if tdelta.days > exp_length:
                logger.debug(user_info['username'] + ' has old flair')
                currentDB.remove(find_stuff['username'] == user_info['username'])
            else:
                user = setUser(user_info['username'])
                # check if user is valid
                if user is not None:
                    sub.current_users.append(user)
        logger.info('Read all current users\n')

        expiredDB = TinyDB(sub_name + '/expired.json')
        for username in expiredDB:
            user = setUser(username['username'])
            if user is not None:
                logger.debug(username['username'] + ' added to expired list')
                sub.expired_users.append(user)
        logger.info('All users read from expired list\n')

        flair_imgDB = TinyDB(sub_name + '/flair_img.json')
        for username in flair_imgDB:
            user = setUser(username['username'])
            if user is not None:
                sub.flair_img.append(user)
        logger.info('All users read from flair image permission list\n')

    def save_sub_status(self):
        try:
            with open(self.sub_name + '/sub_status.json', 'w') as fp:
                json.dump(self.sub_status, fp)
        except Exception:
            logger.exception('Error writing sub_status.json')


# Flair all users in users_and_flair
    def flairUsers(sub):
        sub_obj = sub.sub_obj
        logger.info('Users and corresponding flair:\n')
        for username in sub.users_and_flair:
            user = setUser(username)
            flair = sub.users_and_flair[username]['text']
            css = sub.users_and_flair[username]['css']
            sub_obj.flair.set(user, flair, css)
            logger.debug(username + ': ' + flair)
        sub.users_and_flair.clear()

    # Flair one user from users_and_flair
    def flairUser(sub, user, flair_text):
        sub_obj = sub.sub_obj
        sub_obj.flair.set(user, flair_text)
        logger.info('Flaired user: ' + user + '\tFlair: ' + flair_text)

    # Concatonate flair with existing
    def appendFlair(sub, user, new_flair, css):
        username = str(user)
        if username in sub.users_and_flair:
            hold_flair = sub.users_and_flair[username]['text']
            hold_flair += ' | ' + new_flair
            flair_info = {'text': hold_flair, 'css': css}
            sub.users_and_flair.update({username: flair_info})
        else:
            sub.users_and_flair[username] = {'text': new_flair, 'css': css}

    # Add user to sub whitelist
    def addWhitelist(sub, username):
        whitelistDB = TinyDB(sub.sub_name + '/whitelist.json')
        whitelistDB.insert({'username': username})
        sub.whitelist.append(username)
        logger.info(username + ' added to whitelist')

    # Add user to sub graylist
    def addGraylist(sub, username):
        graylistDB = TinyDB(sub.sub_name + '/graylist.json')
        graylistDB.insert({'username': username})
        sub.graylist.append(username)
        logger.info(username + ' added to graylist')

    # Add a user to the expired list and database
    def addExpired(sub, user):
        username = str(user)
        expiredDB = TinyDB(sub.sub_name + '/expired.json')
        expiredDB.insert({'username': username})
        sub.expired_users.append(user)
        logger.info('User: ' + username + ' added to expired list')

    # Add an image flair option to the image flair list
    def addImgFlair(sub, username):
        flair_imgDB = TinyDB(sub.sub_name + '/flair_img.json')
        flair_imgDB.insert({'username': username})
        sub.flair_img.append(username)
        logger.info(username + ' added to flair image permission list')

    # Turn user data into a user object
    def makeUser(sub, user, username, date_created, analysis_time, latest_comment_id, latest_post_id, latest_stale_comment_id, latest_stale_post_id,
                 total_comment_karma, total_post_karma, total_karma, comment_karma_counter, post_karma_counter, pos_comment_counter, neg_comment_counter,
                 pos_post_counter, neg_post_counter, pos_QC_counter, neg_QC_counter):
        sub.current_users.append(user)
        return User(sub, username, date_created, analysis_time, latest_comment_id, latest_post_id, latest_stale_comment_id, latest_stale_post_id,
                    total_comment_karma, total_post_karma, total_karma, comment_karma_counter, post_karma_counter, pos_comment_counter, neg_comment_counter,
                    pos_post_counter, neg_post_counter, pos_QC_counter, neg_QC_counter)

    # Turn a string into a dictionary
    def makeDict(sub, info_str):
        info_counter = Counter()
        info_list = info_str.split()
        while len(info_list) >= 2:
            info_counter[info_list.pop()] = int(info_list.pop())
        return info_counter

    def get_user_analysis_age(self, username):
        try:
            user_db = TinyDB(self.sub_name + '/userInfo.json')
            u = user_db.search(Query()['username'] == username)
            if u:
                td = datetime.utcnow() - dateutil.parser.parse(u[0]['analysis_time'])
                return td.total_seconds()
        except Exception:
            logger.exception('Error finding user')
            pass

    def delete_user(self, username):
        user_db = TinyDB(self.sub_name + '/userInfo.json')
        logger.info('Deleting user: {username}'.format(username=username))
        user_db.remove(where('username') == username)

    def get_oldest_user(self):
        user_db = TinyDB(self.sub_name + '/userInfo.json')
        u = sorted(user_db.all(), key=lambda record: record['analysis_time'])[0]
        td = relativedelta.relativedelta(datetime.utcnow(), dateutil.parser.parse(u['analysis_time']))
        username = u['username']
        logger.info('Oldest user {username}: {td}'.format(username=username, td=td))
        return username

    # Retrieve a user's data from the database
    def getUserInfo(sub, username):
        userDB = TinyDB(sub.sub_name + '/userInfo.json')
        try:
            info_dict = userDB.search(find_stuff['username'] == username)[0]
        except IndexError:
            logger.debug('User: ' + username + ' not found')
            return None

        date_created = info_dict['date_created']
        analysis_time = info_dict['analysis_time']
        latest_comment_id = info_dict.get('latest_comment_id')
        latest_stale_comment_id = info_dict.get('latest_stale_comment_id')
        latest_post_id = info_dict.get('latest_post_id')
        latest_stale_post_id = info_dict.get('latest_stale_post_id')
        total_comment_karma = info_dict['total_comment_karma']
        total_post_karma = info_dict['total_post_karma']
        total_karma = info_dict['total_karma']
        comment_karma_counter = sub.makeDict(info_dict['comment_karma_counter'])
        post_karma_counter = sub.makeDict(info_dict['post_karma_counter'])
        pos_comment_counter = sub.makeDict(info_dict['pos_comment_counter'])
        neg_comment_counter = sub.makeDict(info_dict['neg_comment_counter'])
        pos_post_counter = sub.makeDict(info_dict['pos_post_counter'])
        neg_post_counter = sub.makeDict(info_dict['neg_post_counter'])
        pos_QC_counter = sub.makeDict(info_dict['pos_QC_counter'])
        neg_QC_counter = sub.makeDict(info_dict['neg_QC_counter'])

        return User(sub, username, date_created, analysis_time, latest_comment_id, latest_post_id, latest_stale_comment_id, latest_stale_post_id,
                    total_comment_karma, total_post_karma, total_karma, comment_karma_counter, post_karma_counter, pos_comment_counter, neg_comment_counter,
                    pos_post_counter, neg_post_counter, pos_QC_counter, neg_QC_counter)

    # Check if user should be analyzed and if they are accessible
    def checkUser(sub, user):
        if user not in sub.whitelist and user not in sub.graylist and user not in sub.expired_users and str(
                user) not in sub.mods and user not in sub.current_users:
            try:
                user.fullname
            except (prawcore.exceptions.NotFound, AttributeError):
                return False
            return True
        else:
            return False

    def should_act_on(sub, user):
        if user not in sub.whitelist and user not in sub.graylist and str(user) not in sub.mods:
            return True
        else:
            return False

    # Clear the expired database after the users are analyzed
    def dropExpired(sub):
        expiredDB = TinyDB(sub.sub_name + '/expired.json')
        logger.info(str(len(expiredDB)))
        expiredDB.purge()
        logger.info('Expired user database was purged')
        sub.expired_users.clear()
