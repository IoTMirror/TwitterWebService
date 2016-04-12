import os
import tweepy
import json
import urllib.parse
import psycopg2
import psycopg2.extras
import flask

app = flask.Flask(__name__)

consumer_key = os.environ['TWITTER_CONSUMER_KEY']
consumer_secret = os.environ['TWITTER_CONSUMER_KEY_SECRET']

class TweeterUser:
  pass

class Tweet:
  pass

class TokensDatabase:
  def __init__(self, db_url, table_prefix=""):
    self.url = urllib.parse.urlparse(db_url)
    self.table_prefix=table_prefix
  
  def getUserTokens(self, userID):
    url = self.url
    con = psycopg2.connect(database=self.url.path[1:], user=self.url.username,
			  password=self.url.password,host=self.url.hostname,
			  port=self.url.port
	  )
    cur = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT access_token, access_token_secret FROM "+self.table_prefix+"access_tokens WHERE user_id=(%s);",[userID])
    row = cur.fetchone()
    cur.close()
    con.close()
    return row
  
  def deleteUserTokens(self, userID):
    con = psycopg2.connect(database=self.url.path[1:], user=self.url.username,
			  password=self.url.password,host=self.url.hostname,
			  port=self.url.port
	  )
    cur = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("DELETE FROM "+self.table_prefix+"access_tokens WHERE user_id=(%s);",[self.table_prefix,userID])
    con.commit()
    cur.close()
    con.close()
  
class ObjectJSONEncoder(json.JSONEncoder):
  def default(self,obj):
    if hasattr(obj, '__dict__'):
      return obj.__dict__
    else:
      return json.JSONEncoder.default(self,obj)

#returns info about user specified by userID
@app.route('/users/<userID>', methods=['GET'])
def userInfo(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = TokensDatabase(os.environ['DATABASE_URL'],"twitter_").getUserTokens(userID)
  if(tokens is None):
    return ('',404)
  try:
    auth.set_access_token(tokens["access_token"], tokens["access_token_secret"])
    api = tweepy.API(auth)
    user_data = api.me()
    user = TweeterUser()
    user.name=user_data.name;
    user.screen_name=user_data.screen_name;
    user.id=user_data.id;
  except tweepy.TweepError as e:
    return ('',e.response.status_code)
  return json.dumps(user,cls=ObjectJSONEncoder)

#deletes access tokens related to the user specified by userID
@app.route('/users/<userID>', methods=['DELETE'])
def deleteUserData(userID):
  TokensDatabase(os.environ['DATABASE_URL']).deleteUserTokens(userID)
  return ('',204)

#returns tweets form user's (specified by userID) home_timeline
@app.route('/users/<userID>/home_timeline')
def tweets(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = TokensDatabase(os.environ['DATABASE_URL'],"twitter_").getUserTokens(userID)
  if(tokens is None):
    return ('',404)
  auth.set_access_token(tokens["access_token"], tokens["access_token_secret"])
  api = tweepy.API(auth)
  tweets = []
  try:
    for status in tweepy.Cursor(api.home_timeline).items(20):
      tweet = Tweet()
      tweet.id=status.id
      tweet.text=status.text
      tweet.created_at=status._json['created_at']
      tweet.user=TweeterUser()
      tweet.user.name=status.user.name
      tweet.user.id=status.user.id
      tweet.user.screen_name=status.user.screen_name
      tweets.append(tweet)
  except tweepy.TweepError as e:
    return ('',e.response.status_code)
  return json.dumps(tweets,cls=ObjectJSONEncoder)

if __name__ == '__main__':
  app.run()

