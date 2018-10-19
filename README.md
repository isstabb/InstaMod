# InstaMod
## An Automoderator-like bot which allows moderators to create a custom rule set based on a user's account history

### InstaMod is capable of automatically assigning users' flair, advanced thread locking, subreddit-wide filtering, creating a subreddit progression system, and more. 

It can also work in conjunction with AutoMod via user flair text. Below I will describe the different rule types and give an example of how some of the systems work.

-----
### Automatic User Flair:
Features, such as the subreddit progression system, can be displayed in a user's flair and keep it continuously updated. These flairs consist of a serries of tags that moderators can design rules for. Everything is able to be customized from the provided configuration file. Each rule can use one data point from this list of possible user information:
* Total comment karma/total post karma/total karma
* Comment/Post karma borken down by subreddit
* Positive/Negative posts/comments broken down by subreddit
* Comment count based on a custom comment filter

### Subreddit Tags:
Moderators can provide lists of subreddits which the bot will collect information on. This information can be used to create tags for users' flair. The sub tag's rules can be set to display a user's top 3 most used communities from a list of related subreddits. It could also be designed to show all the subreddits where a user has been consistently downvoted. Here are some of this tag's unique characteristics:
* Abbreviations for subreddit names
* Grouping subreddits
* Showing the top/bottom X number of subreddits that match a rule

### Subreddit Progression:
As a user participates more and more in the community, their flair can change to represent their involvement. Certain tags, or levels of user participation, can grant the user access to special priveledges. This includes the ability to assign themself custom flair and the ability to append their automatic flair with a designated list of :images:. For instance, you could give every user with less than 25 positive comments in your subreddit a tag that says "New Here". While every user with over 100 positive comments gets to overwrite their automatic flair.

### Advanced Thread/Sub Locking:
Traditional thread locking is all-or-nothing and AutoModerator can only filter users' comments based on flair text and account age. With InstaMod, a post's comment section can be filtered through a rule. If a user doesn't meet the requirements, then their comment can either be removed or marked spam. There is also a way to automatically notify the user of their comment's deletion. Moderators simply have to assign a post a specific flair for it to be locked. This type of rule can also be applied to the subreddit as a whole, and is activated/deactivated via PM.

### Custom Rate-limiting (Comming Soon):
Reddit has a built in rate-limit system to prevent spam, but with InstaMod this can be expanded and customized to ensure that new users in your subreddit cannot spam comments or submissions. Moderators can design the bot to prevent users with less than 20 positive comments from submitting more than 5 posts in a day, or it could prevent users with more negative than positive comments from commenting more than once a day. The options are endless!

### Getting Started:
#### Preparation
You will need to create a new reddit account to serve as the bot.  Add this user as a moderator in subreddits you want InstaMod to work in.  It should be sufficient to only give this user the following mod permissions:  `flair, mail, posts, wiki`

While logged in as the bot user, go to `https://www.reddit.com/prefs/apps/` and create an app as a "script for personal use" with the following values:

```text
name: InstaMod
redirect uri: http://www.example.com/unused/redirect/uri
```
  
After creating the app you will need to copy the 14-character client id from below "personal use script", and the 27-character secret into the step below.

Add a file named `praw.ini` in this directory.  The contents should look like:

```$ini
[InstaMod]
username=<bot user name>
password=<bot password>
client_id=<client id from above step>
client_secret=<secret from above step>
user_agent=InstaMod
app_debugging=true
``` 

Use the Config Documentation and Sample Configuration Layout to come up with a subreddit configuration that has the features and configurations you want.

Add a new wiki at `https://www.reddit.com/r/yoursubreddit/wiki/instamodsettings`.  Set the permissions on the new wiki to `only mods may edit and view`.  Edit the wiki content and paste the entire configuration from the above step and save it.

#### Running the script

You'll need python2 or python3 and should use a virtual environment (outside the scope of this README).  Once you have the python virtual environment activated, you should run:

`pip install -r requirements.txt`

This will install the needed python dependencies.

Run the InstaMod script from within your python virtual environment like so:

`python InstaMod.py -h` 

This will output a description of various command line arguments you might want to tweak.

Run the script and process InstaMod actions:

`python InstaMod.py yoursubreddit anothersubreddit`

Where the arguments are the subreddits to process InstaMod on, as well as adding any command line arguments you want to use.

The first time InstaMod runs, it will take far longer than each successive run because it has no user or post history.  You'll know it is caught up when you actually see it sleep.

#### Running the script as a service
When it appears that InstaMod is doing what you want it to it is time to install it as a service.  This varies across platforms and hosting services so you'll have to search around.  You should run the script using the python from the virtual environment (run `which python` with the virtual environment activated).