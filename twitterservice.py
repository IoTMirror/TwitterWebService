import flask
import json
import os
import psycopg2
import psycopg2.extras
import tweepy
import requests
import urllib.parse
from iotmirror_commons.oauth_tokens import OAuthTokensDatabase


app = flask.Flask(__name__)

consumer_key = os.environ['TWITTER_CONSUMER_KEY']
consumer_secret = os.environ['TWITTER_CONSUMER_KEY_SECRET']

class TweeterUser:
  pass

class Tweet:
  pass
  
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
  tokens = OAuthTokensDatabase(os.environ['DATABASE_URL'],"twitter_").getUserAccessTokens(userID)
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
@app.route('/users/<userID>/access_tokens', methods=['DELETE'])
def deleteUserAccessTokens(userID):
  OAuthTokensDatabase(os.environ['DATABASE_URL'],"twitter_").deleteUserAccessTokens(userID)
  return ('',204)

#returns tweets form user's (specified by userID) home_timeline
@app.route('/users/<userID>/home_timeline')
def tweets(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = OAuthTokensDatabase(os.environ['DATABASE_URL'],"twitter_").getUserAccessTokens(userID)
  if(tokens is None):
    return ('',404)
  auth.set_access_token(tokens["access_token"], tokens["access_token_secret"])
  api = tweepy.API(auth)
  tweets = []
  hashtags = []
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
      hashtags.extend([hashtag['text'] for hashtag in status.entities['hashtags']])
  except tweepy.TweepError as e:
    return ('',e.response.status_code)
  advservice_url = os.environ.get('ADVSERVICE_URL')
  if advservice_url is not None:
    for hashtag in hashtags:
      try:
        requests.put(advservice_url+"/users/"+userID+"/tweeter/hashtags/"+hashtag)
      except requests.exceptions.RequestException:
        pass
  return json.dumps(tweets,cls=ObjectJSONEncoder)

if __name__ == '__main__':
  port = int(os.environ.get('PORT',5000))
  app.run(host='0.0.0.0',port=port)

