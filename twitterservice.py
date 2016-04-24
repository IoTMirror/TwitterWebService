import flask
import json
import os
import psycopg2
import psycopg2.extras
import tweepy
import requests
import urllib.parse
from iotmirror_commons.oauth_tokens import AccessTokensDatabase, RequestTokensDatabase


app = flask.Flask(__name__)

app.secret_key = os.environ['APP_SESSION_SECRET_KEY']
consumer_key = os.environ['TWITTER_CONSUMER_KEY']
consumer_secret = os.environ['TWITTER_CONSUMER_KEY_SECRET']
dburl = os.environ['DATABASE_URL']
access_tokens_table = "twitter_access_tokens"
request_tokens_table = "twitter_request_tokens"
atdb = AccessTokensDatabase(dburl,access_tokens_table)
rtdb = RequestTokensDatabase(dburl,request_tokens_table)

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

#starts signin process for given user
@app.route('/signin/<userID>', methods=['GET'])
def signinUser(userID):
  callback_url = os.environ.get('TWITTER_CALLBACK_URL',None)
  auth = tweepy.OAuthHandler(consumer_key,consumer_secret,callback_url)
  redirect_url = auth.get_authorization_url(True);
  rtdb.insertRequestToken(auth.request_token["oauth_token"],auth.request_token["oauth_token_secret"],userID)
  return flask.redirect(redirect_url)

#exchanges request token for access tokens
@app.route('/signin', methods=['GET'])
def signinComplete():
  oauth_request_token = flask.request.args.get('oauth_token',None)
  oauth_verifier = flask.request.args.get('oauth_verifier',None)
  denied = flask.request.args.get('denied',None)
  if (oauth_request_token is None or oauth_verifier is None) and denied is None:
    flask.abort(400)
  if (denied is not None):
    rtdb.deleteRequestToken(denied)
    return ""
  twitter_request_token = rtdb.getRequestToken(oauth_request_token)
  if(twitter_request_token is None):
    flask.abort(404)
  rtdb.deleteRequestToken(oauth_request_token)
  auth = tweepy.OAuthHandler(consumer_key,consumer_secret)
  auth.request_token={"oauth_token":twitter_request_token["request_token"],
                      "oauth_token_secret":twitter_request_token["request_token_secret"]}
  try:
    auth.get_access_token(oauth_verifier)
    atdb.insertUserAccessTokens(twitter_request_token["user_id"],auth.access_token,auth.access_token_secret)
  except tweepy.TweepError:
    flask.abort(401)
  except psycopg2.IntegrityError:
    atdb.updateUserAccessTokens(twitter_request_token["user_id"],auth.access_token,auth.access_token_secret)
  return ""

#deletes request tokens related to the user specified by userID
@app.route('/users/<userID>/request_tokens', methods=['DELETE'])
def deleteUserRequestTokens(userID):
  rtdb.deleteUserRequestTokens(userID)
  return ('',204)

#returns info about user specified by userID
@app.route('/users/<userID>', methods=['GET'])
def userInfo(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = atdb.getUserAccessTokens(userID)
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
  atdb.deleteUserAccessTokens(userID)
  return ('',204)

#returns tweets form user's (specified by userID) home_timeline
@app.route('/users/<userID>/home_timeline')
def tweets(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = atdb.getUserAccessTokens(userID)
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

